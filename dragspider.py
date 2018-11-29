import json
import os
import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import Rule
from pathlib import Path
from cryptography.fernet import Fernet
import requests
import re


class DragspiderSpider(scrapy.Spider):
    name = 'dragspider'
    allowed_domains = ['dragdis.com']
    login_url = 'https://dragdis.com/Account/Login/'
    start_urls = ['https://dragdis.com']
    extract_path_available = False

    rules = (
        Rule(LinkExtractor(allow=()),
             callback='parse_item', follow=True),
    )

    def __init__(self, folder_id='', start_page_number='', max_page_number='', *args, **kwargs):
        super(DragspiderSpider, self).__init__(*args, **kwargs)
        self.start_page_number = int(start_page_number)
        self.max_page_number = int(max_page_number) + 1
        self.folder_id = int(folder_id)

    def parse(self, response):
        token = response.xpath('//*[@name="__RequestVerificationToken"]/@value').extract_first()

        data = {
            "Username": 'UserName',
            "Password": 'UserPassword',
            "__RequestVerificationToken": token
        }

        yield scrapy.FormRequest(url=self.login_url, formdata=data, callback=self.after_login)

    def after_login(self, response):
        # check login succeed before going on
        if str(response.body).find('DragdisUsername') != -1:
            self.logger.debug("Login Succeeded")

        # generate api get request url list
        url_list = []
        for i in range(self.start_page_number, self.max_page_number):
            folder_url = "https://dragdis.com/api/item/list?folderId=" + str(self.folder_id) + "&page=" + str(i) + \
                         "&searchValue=&thumbnailSize=s23"
            url_list.append(folder_url)

        lst = []
        for link in url_list:
            lst.append(scrapy.FormRequest(link, callback=self.parse_item))  # alternative function scrapy.Request()

        return lst

    def parse_item(self, response):
        jsonresponse = json.loads(response.body_as_unicode())

        for respo in jsonresponse:
            self.save_image(respo)

    def update_mapping_file(self, map_file_path, url_referer, date_created, original_file_name, url_status):
        with open(map_file_path, 'a', encoding='utf-8') as file:  # encoding added to avoid UnicodeEncodeError
            file.write(
                ("Refer Url: " + url_referer + "\n" + "Date Created: " + date_created + "\n" +
                 "Formatted File Name: " + original_file_name + "\n" +
                 "--------------- " + url_status + " ----------------------------" + "\n\n"))

    def update_error_file(self, data_folder, url_referer, date_created, file_name, blob_url):
        info_error_file_path = data_folder / 'Errors.txt'
        with open(info_error_file_path, 'a', encoding='utf-8') as file:  # 'a' will append the data to the end of file
            file.write(
                ("!!!!! Erro Occurred in Refer Url: " + url_referer + "\n" + "Date Created: " + date_created + "\n" +
                 "Formatted File Name: " + file_name + "\n" +
                 "!!!! Blob file url: " + blob_url + "!!!!!!!!!!!!!!!!!!!!!!!!!" + "\n\n"))
        self.logger.error("File Referer:  ", url_referer, " error occurred.")

    def save_to_disk(self, complete_name, image_content, info_mapping_file_path, url_referer, date_created,
                     formatted_file_name):

        with open(complete_name, 'wb') as f:
            f.write(image_content)

        self.update_mapping_file(info_mapping_file_path, url_referer, date_created, formatted_file_name,
                                     "image saved")

    def save_image(self, json_obj):
        file_extracting_folder = 'extracted'
        url_referer = json_obj['Referer']
        date_created = json_obj['DateCreated']

        formatted_file_name = re.sub('\W+', '_', url_referer)
        file_name = formatted_file_name[:190]  # trimmed due to avoid file length exception
        item_link = json_obj['UniqueItem'].get('Original')
        folder_name = str(json_obj['FolderId'])

        if not self.extract_path_available:
            try:
                # Create base directory
                os.mkdir(file_extracting_folder)
                self.extract_path_available = True
            except Exception as e:
                self.logger.info("Directory ", file_extracting_folder, " already exists")

        path = Path('extracted') / folder_name
        data_folder = Path("extracted/" + folder_name + "/")  # instead of os.path.join, path is used
        info_mapping_file_path = data_folder / 'mapping.txt'  # instead of os.path.join, path is used

        try:
            response = requests.get(item_link, stream=True)
        except Exception as e:
            self.update_mapping_file(info_mapping_file_path, url_referer, date_created, formatted_file_name, "!!!!! image not available !!!!!")
            return

        try:
            # Create target data directory
            os.mkdir(path)
            self.logger.info("Directory ", folder_name, " Created ")
        except FileExistsError:
            self.logger.info("Directory ", folder_name, " already exists")

        try:
            if response.status_code == 200:
                complete_name = data_folder / (file_name + ".jpg")

            if not Path(complete_name).exists():
                self.save_to_disk(complete_name, response.content, info_mapping_file_path, url_referer, date_created,
                                  formatted_file_name)
            else:
                complete_name = data_folder / (file_name + "_" + re.sub('\W+', '_', date_created) + ".jpg")
                self.save_to_disk(complete_name, response.content, info_mapping_file_path, url_referer, date_created,
                                  formatted_file_name)

        except Exception as e:
            self.update_error_file(data_folder, url_referer, date_created, formatted_file_name, item_link)