import codecs
import threading
import os
import re
import queue
import shutil
import sys
import uuid
import zipfile

from bs4 import BeautifulSoup
import requests

from global_variable import HAS_QT, HEADERS

if HAS_QT:
    from global_variable import SENDER

_download_queue = queue.Queue()
_PROGRESS_LOCK = threading.Lock()


class Epub():
    """
    deal with epub

    Attributes:
        volume_name: A string represents the volume name
        volume_number: A string represents the volume number
        volume_author: A string represents the author
        volume_illustrator: A string represents the illustrator
        volume_introduction: A string represents the introduction
        volume_cover_url: A string represents the cover_url
        chapter_links: A string represents the chapter links
        output_dir: A stirng represents the epub save path
        cover_path: A string represents the cover path
        book_name: A string represents the book name
        publisher_name: A string represents the book publisher
        uuid: A string represents the book uuid
        chapter: A list represents the chapter
        base_path: A string represents the epub temp path

    """

    def __init__(self, output_dir=None, cover_path=None, single_thread=False, **kwargs):
        self.output_dir = output_dir
        self.cover_path = cover_path
        self.single_thread = single_thread

        self.uuid = str(uuid.uuid1())

        self.chapters = kwargs['chapter']
        self.volume_name = kwargs['volume_name']
        self.volume_number = kwargs['volume_number']
        self.author = kwargs['author']
        self.illustrator = kwargs['illustrator']
        self.publisher_name = kwargs['publisher_name']
        self.introduction = kwargs['introduction']
        self.cover_url = kwargs['cover_url']
        self.book_name = kwargs['book_name']
        self.base_path = ''
        self.pictures = []

        self.finished_picture_number = 0


    def create_folders(self):
        if not os.path.exists(self.base_path):
            os.mkdir(self.base_path)
        if not os.path.exists(os.path.join(self.base_path, 'Text')):
            os.mkdir(os.path.join(os.path.join(self.base_path, 'Text')))
        if not os.path.exists(os.path.join(self.base_path, 'Styles')):
            os.mkdir(os.path.join(os.path.join(self.base_path, 'Styles')))
        if not os.path.exists(os.path.join(self.base_path, 'Images')):
            os.mkdir(os.path.join(os.path.join(self.base_path, 'Images')))
        shutil.copy2('./templates/style.css', os.path.join(os.path.join(self.base_path, 'Styles')))

    def move_or_download_cover(self):
        if not self.cover_path:
            self.pictures.append(self.cover_url)
        else:
            temp_cover_path = os.path.join(os.path.join(self.base_path, 'Images'), self.cover_path.split('/')[-1])
            shutil.copyfile(self.cover_path, temp_cover_path)

    @staticmethod
    def print_info(info):
        try:
            print(info)
            if HAS_QT:
                SENDER.sigChangeStatus.emit(info)
        except UnicodeDecodeError as e:
            print('Ignored:', e)

    @staticmethod
    def emit_info(info):
        if HAS_QT:
            SENDER.sigChangeStatus.emit(info)

    def download_progress(self, url):
        with _PROGRESS_LOCK:
            self.finished_picture_number += 1
            self.emit_info(str(self.finished_picture_number) + '/' + str(len(self.pictures)) + url)
            sharp_number = round(self.finished_picture_number / len(self.pictures) * 60)
            space_number = 60 - sharp_number
            sys.stdout.write(
                '\r' + str(self.finished_picture_number) + '/' + str(
                    len(self.pictures)) + '[' + '#' * sharp_number + ' ' * space_number + ']')
            sys.stdout.flush()

    def download_picture(self):
        """
        download pictures from _download_queue
        """
        while not _download_queue.empty():
            url = _download_queue.get()
            try:
                path = os.path.join(os.path.join(self.base_path, 'Images'), url.split('/')[-1])
                if not os.path.exists(path):
                    r = requests.get(url, headers=HEADERS, stream=True)
                    if r.status_code == requests.codes.ok:
                        temp_chunk = r.content
                        with open(path, 'wb') as f:
                            f.write(temp_chunk)
                    else:
                        print(r.status_code)
                self.download_progress(url)
            except Exception as e:
                print(e)
                _download_queue.put(url)
            finally:
                _download_queue.task_done()

    @staticmethod
    def sort_itemref(file_name):
        m = re.match('\d+', file_name)
        if m:
            return int(m.group(0))
        else:
            return -1

    @staticmethod
    def file_to_string(file_path):
        """
        read the file as a tring

        Return:
            A string
        """
        with codecs.open(file_path, 'r', 'utf-8') as f:
            return ''.join(f.readlines())

    def create_cover_html(self):
        cover_name = self.cover_url.split('/')[-1]
        cover_html = self.file_to_string('./templates/Cover.html')
        final_cover_html = cover_html.format(cover_name=cover_name, introduction=self.introduction)
        return final_cover_html

    @staticmethod
    def write_html(html, file_path):
        with codecs.open(file_path, 'w', 'utf-8') as f:
            f.write(BeautifulSoup(html).prettify())

    def create_chapter_html(self):
        chapter_html = self.file_to_string('./templates/Chapter.html')
        final_chapter_htmls = []
        for chapter in sorted(self.chapters, key=lambda x: x[0]):
            content = []
            chapter_name = chapter[1]

            for line in chapter[2]:
                if line.startswith('/illustration/'):
                    image_url = 'http://lknovel.lightnovel.cn' + line
                    self.pictures.append(image_url)
                    image = '<div class="illust"><img alt="" src="../Images/' + image_url.split('/')[
                        -1] + '" /></div>\n<br/>'
                    content.append(image)
                else:
                    content.append('<p>' + line + '</p>')
            one_chapter_html = chapter_html.format(chapter_name=chapter_name, content='\n'.join(content))
            final_chapter_htmls.append(one_chapter_html)
        return final_chapter_htmls

    def create_title_html(self):
        title_html = self.file_to_string('./templates/Title.html')
        author = '<p class="titlep">作者：' + self.author + '</p>'
        illustrator = '' if not self.illustrator else '<p class="titlep">插画：' + self.illustrator + '</p>'
        final_title_html = title_html.format(book_name=self.book_name, volume_name=self.volume_name,
                                             volume_number=self.volume_number, author=author,
                                             illustrator=illustrator)
        return final_title_html

    def create_contents_html(self):
        contents_html = self.file_to_string('./templates/Contents.html')
        contents = []
        for i in sorted(self.chapters, key=lambda chapter: chapter[0]):
            contents.append('<li class="c-rules"><a href="../Text/' + str(i[0]) + '.html">' + i[1] + '</a></li>')
        final_contetns_html = contents_html.format(contents='\n'.join(contents))
        return final_contetns_html

    def download_all_pictures(self):
        for picture in self.pictures:
            _download_queue.put(picture)
        th = []
        self.print_info('Start downloading pictures, total number:' + str(len(self.pictures)))
        for i in range(5):
            t = threading.Thread(target=self.download_picture)
            t.start()
            th.append(t)
        for t in th:
            t.join()

    def create_content_opf_html(self):
        content_opf_html = self.file_to_string('./templates/content.opf')
        cover_name = self.cover_url.split('/')[-1]

        file_paths = []
        for dir_path, dir_names, file_names in os.walk(os.path.join(self.base_path, 'Text')):
            for file in file_names:
                if file != 'toc.ncx':
                    file_paths.append(
                        '<item href="Text/' + file + '" id="' + file + '" media-type="application/xhtml+xml" />')
            break

        file_paths.append('<item href="Styles/style.css" id="style.css" media-type="text/css" />')

        for dir_path, dir_names, file_names in os.walk(os.path.join(self.base_path, 'Images')):
            for file in file_names:
                postfix = file.split('.')[-1]
                postfix = 'jpeg' if postfix == 'jpg' else postfix
                file_paths.append(
                    '<item href="Images/' + file + '" id="' + file + '" media-type="image/' + postfix + '" />')
            break

        chapter_orders = []

        for dir_path, dir_names, file_names in os.walk(os.path.join(self.base_path, 'Text')):
            for file in sorted(file_names, key=self.sort_itemref):
                if file not in ('Cover.html', 'Title.html', 'Contents.html'):
                    chapter_orders.append('<itemref idref="' + file + '" />')
        final_content_opf_html = content_opf_html.format(book_name=self.book_name, uuid=self.uuid,
                                                         cover_name=cover_name,
                                                         author=self.author, file_paths='\n'.join(file_paths),
                                                         chapter_orders='\n'.join(chapter_orders),
                                                         descriptions=self.introduction, publisher_name=self.publisher_name)
        return final_content_opf_html

    def create_toc_html(self):
        toc_html = self.file_to_string('./templates/toc.ncx')
        nav = []
        playorder = 4
        for i in sorted(self.chapters, key=lambda chapter: chapter[0]):
            nav.append(
                '<navPoint id="' + str(i[0]) + '" playOrder="' + str(playorder) + '">\n<navLabel>\n<text>' + i[
                    1] + '</text>\n</navLabel>\n<content src="Text/' + str(i[0]) + '.html"/>\n</navPoint>')
            playorder += 1
        final_toc_html = toc_html.format(uuid=self.uuid, book_name=self.book_name, author=self.author,
                                         nav='\n'.join(nav))
        return final_toc_html

    def create_html(self):
        """
        create the html file for epub
        """
        html_path = os.path.join(self.base_path, 'Text')

        cover_html = self.create_cover_html()
        self.write_html(cover_html, os.path.join(html_path, 'Cover.html'))

        chapter_htmls = self.create_chapter_html()
        for i, chapter_html in enumerate(chapter_htmls):
            self.write_html(chapter_html, os.path.join(html_path, str(i) + '.html'))

        title_html = self.create_title_html()
        self.write_html(title_html, os.path.join(html_path, 'Title.html'))

        contents_html = self.create_contents_html()
        self.write_html(contents_html, os.path.join(html_path, 'Contents.html'))

        self.download_all_pictures()

        content_opf_html = self.create_content_opf_html()
        self.write_html(content_opf_html, os.path.join(self.base_path, 'content.opf'))

        toc_html = self.create_toc_html()
        self.write_html(toc_html, os.path.join(self.base_path, 'toc.ncx'))

    def zip_files(self):
        folder_name = os.path.basename(self.base_path)
        with zipfile.ZipFile(folder_name + '.epub', 'w', zipfile.ZIP_DEFLATED) as z:
            for dir_path, dir_names, file_names in os.walk(self.base_path):
                for file in file_names:
                    f = os.path.join(dir_path, file)
                    z.write(f, 'OEBPS//' + f[len(self.base_path) + 1:])
            z.write('./files/container.xml', 'META-INF//container.xml')
            z.write('./files/mimetype', 'mimetype')

    def move_epub_file(self):
        folder_name = os.path.basename(self.base_path)
        if os.path.exists(os.path.join(self.output_dir, folder_name + '.epub')):
            if HAS_QT:
                SENDER.sigWarningMessage.emit('文件名已存在', 'epub保存在lknovel文件夹')
                SENDER.sigButton.emit()
        else:
            shutil.move(folder_name + '.epub', self.output_dir)
            if HAS_QT:
                SENDER.sigInformationMessage.emit('已生成', folder_name + '.epub')
                SENDER.sigButton.emit()

    def generate_epub(self):
        """generate epub file from novel"""
        folder_name = re.sub(r'[<>:"/\\|\?\*]', '_', self.book_name)
        self.base_path = os.path.abspath(folder_name)
        self.create_folders()
        self.move_or_download_cover()

        self.create_html()

        self.zip_files()
        self.print_info('\n已生成：' + self.book_name + '.epub\n\n')

        # delete temp file
        shutil.rmtree(self.base_path)

        # move file
        if self.output_dir:
            self.move_epub_file()
