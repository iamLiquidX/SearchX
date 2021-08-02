import os
import pickle
import re
import requests
import logging

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from telegram import InlineKeyboardMarkup
from bot.helper.telegram_helper import button_builder
from bot import DRIVE_NAME, DRIVE_ID, INDEX_URL, telegra_ph

LOGGER = logging.getLogger(__name__)
logging.getLogger('googleapiclient.discovery').setLevel(logging.ERROR)

SIZE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
TELEGRAPHLIMIT = 90

class GoogleDriveHelper:
    def __init__(self, name=None, listener=None):
        self.__G_DRIVE_TOKEN_FILE = "token.pickle"
        # Check https://developers.google.com/drive/scopes for all available scopes
        self.__OAUTH_SCOPE = ['https://www.googleapis.com/auth/drive']
        self.__service = self.authorize()
        self.telegraph_content = []
        self.path = []

    def get_readable_file_size(self,size_in_bytes) -> str:
        if size_in_bytes is None:
            return '0B'
        index = 0
        size_in_bytes = int(size_in_bytes)
        while size_in_bytes >= 1024:
            size_in_bytes /= 1024
            index += 1
        try:
            return f'{round(size_in_bytes, 2)}{SIZE_UNITS[index]}'
        except IndexError:
            return 'File too large'


    def authorize(self):
        # Get credentials
        credentials = None
        if os.path.exists(self.__G_DRIVE_TOKEN_FILE):
            with open(self.__G_DRIVE_TOKEN_FILE, 'rb') as f:
                credentials = pickle.load(f)
        if credentials is None or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', self.__OAUTH_SCOPE)
                LOGGER.info(flow)
                credentials = flow.run_console(port=0)

            # Save the credentials for the next run
            with open(self.__G_DRIVE_TOKEN_FILE, 'wb') as token:
                pickle.dump(credentials, token)
        return build('drive', 'v3', credentials=credentials, cache_discovery=False)

    def get_recursive_list(self, file, rootid = "root"):
        rtnlist = []
        if not rootid:
            rootid = file.get('teamDriveId')
        if rootid == "root":
            rootid = self.__service.files().get(fileId = 'root', fields="id").execute().get('id')
        x = file.get("name")
        y = file.get("id")
        while(y != rootid):
            rtnlist.append(x)
            file = self.__service.files().get(
                fileId=file.get("parents")[0],
                supportsAllDrives=True,
                fields='id, name, parents'
            ).execute()
            x = file.get("name")
            y = file.get("id")
        rtnlist.reverse()
        return rtnlist

    def drive_query(self, parent_id, search_type, fileName):
        query = ""
        if search_type is not None:
            if search_type == '-d':
                query += "mimeType = 'application/vnd.google-apps.folder' and "
            elif search_type == '-f':
                query += "mimeType != 'application/vnd.google-apps.folder' and "
        var=re.split('[ ._,\\[\\]-]',fileName)
        for text in var:
            query += f"name contains '{text}' and "
        query += "trashed=false"
        if parent_id != "root":
            response = self.__service.files().list(supportsTeamDrives=True,
                                                   includeTeamDriveItems=True,
                                                   teamDriveId=parent_id,
                                                   q=query,
                                                   corpora='drive',
                                                   spaces='drive',
                                                   pageSize=1000,
                                                   fields='files(id, name, mimeType, size, teamDriveId, parents)',
                                                   orderBy='folder, modifiedTime desc').execute()["files"]
        else:
            response = self.__service.files().list(q=query + " and 'me' in owners",
                                                   pageSize=1000,
                                                   spaces='drive',
                                                   fields='files(id, name, mimeType, size, parents)',
                                                   orderBy='folder, modifiedTime desc').execute()["files"]
        return response

    def edit_telegraph(self):
        nxt_page = 1
        prev_page = 0
        for content in self.telegraph_content :
            if nxt_page == 1 :
                content += f'<b><a href="https://telegra.ph/{self.path[nxt_page]}">Next</a></b>'
                nxt_page += 1
            else :
                if prev_page <= self.num_of_path:
                    content += f'<b><a href="https://telegra.ph/{self.path[prev_page]}">Previous</a></b>'
                    prev_page += 1
                if nxt_page < self.num_of_path:
                    content += f'<b> | <a href="https://telegra.ph/{self.path[nxt_page]}">Next</a></b>'
                    nxt_page += 1
            telegra_ph.edit_page(path = self.path[prev_page],
                                 title = 'SearchX',
                                 html_content=content)
        return

    def drive_list(self, fileName):
        search_type = None
        if re.search("^-d ", fileName, re.IGNORECASE):
            search_type = '-d'
            fileName = fileName[ 2 : len(fileName)]
        elif re.search("^-f ", fileName, re.IGNORECASE):
            search_type = '-f'
            fileName = fileName[ 2 : len(fileName)]
        if len(fileName) > 2:
            remove_list = ['A', 'a', 'X', 'x']
            if fileName[1] == ' ' and fileName[0] in remove_list:
                fileName = fileName[ 2 : len(fileName) ]
        msg = ''
        INDEX = -1
        content_count = 0
        reached_max_limit = False
        add_title_msg = True
        for parent_id in DRIVE_ID :
            add_drive_title = True
            response = self.drive_query(parent_id, search_type, fileName)
            #LOGGER.info(f"my a: {response}")

            INDEX += 1
            if response:

                for file in response:

                    if add_title_msg == True:
                        msg = f'<h3>I found these results for your search query: {fileName}</h3><br><b><a href="https://github.com/iamLiquidX/SearchX"> Bot Repo </a></b>'
                        add_title_msg = False
                    if add_drive_title == True:
                        msg += f"<br><b>{DRIVE_NAME[INDEX]}</b><br><br>"
                        add_drive_title = False
                    if file.get('mimeType') == "application/vnd.google-apps.folder":  # Detect Whether Current Entity is a Folder or File.
                        msg += f"🗃️<code>{file.get('name')}</code> <b>(folder)</b><br>" \
                               f"<b><a href='https://drive.google.com/drive/folders/{file.get('id')}'>Google Drive link</a></b>"
                        if INDEX_URL[INDEX] is not None:
                            url_path = "/".join([requests.utils.quote(n, safe='') for n in self.get_recursive_list(file, parent_id)])
                            url = f'{INDEX_URL[INDEX]}/{url_path}/'
                            msg += f'<b> | <a href="{url}">Index link</a></b>'
                    else:
                        msg += f"<code>{file.get('name')}</code> <b>({self.get_readable_file_size(file.get('size'))})</b><br>" \
                               f"<b><a href='https://drive.google.com/uc?id={file.get('id')}&export=download'>Google Drive link</a></b>"
                        if INDEX_URL[INDEX] is not None:
                            url_path = "/".join([requests.utils.quote(n, safe ='') for n in self.get_recursive_list(file, parent_id)])
                            url = f'{INDEX_URL[INDEX]}/{url_path}'
                            msg += f'<b> | <a href="{url}">Index link</a></b>'
                    msg += '<br><br>'
                    content_count += 1
                    if (content_count >= TELEGRAPHLIMIT):
                        reached_max_limit = True


                        LOGGER.info(f"my a: {content_count}")
                        #self.telegraph_content.append(msg)
                        #msg = ""
                        #content_count = 0
                        break

        if msg != '':
            self.telegraph_content.append(msg)

        if len(self.telegraph_content) == 0:
            return "I ..I found nothing of that sort :(", None

        for content in self.telegraph_content :
            self.path.append(telegra_ph.create_page(title = 'SearchX',
                                                    html_content=content )['path'])

        self.num_of_path = len(self.path)
        if self.num_of_path > 1:
            self.edit_telegraph()

        msg = f"Found {content_count}" + ("+" if content_count >= 90 else "") + " results"

        if reached_max_limit:
            msg += ". (Only showing top 90 results. Omitting remaining results)"

        buttons = button_builder.ButtonMaker()
        buttons.buildbutton("Click Here for results", f"https://telegra.ph/{self.path[0]}")

        return msg, InlineKeyboardMarkup(buttons.build_menu(1))
