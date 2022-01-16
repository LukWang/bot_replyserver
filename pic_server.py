import json
import os, random
from botoy import logger, GroupMsg, FriendMsg
from botoy.parser import friend as fp
from botoy.parser import group as gp
import httpx
from .pic_dbi import picDB, cateInfo, picInfo

class PicObj():
    Url: str
    Md5: str


cur_file_dir = os.path.dirname(os.path.realpath(__file__))
pic_dir = ''
try:
    with open(cur_file_dir + '/config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
        pic_dir = config['pic_dir']
except:
    logger.error('config error')
    raise

class pic_server:
    def __init__(self):
        self.db = picDB()
        self.cate_info = cateInfo()
        self.cur_dir = ''
        
    def checkout(self, name, create = False):
        self.cate_info = self.db.get_cate_info(name)
        self.cur_dir = os.path.join(pic_dir, name)
        if not self.cate_info:
            if create:
                if not os.path.exists(self.cur_dir):
                    os.mkdir(self.cur_dir, 666)
                self.db.add_category(name)
                self.cate_info = self.db.get_cate_info(name)
            else:
                return False
        
        return True


    def random_pic(self):
        if self.cate_info.sequence == 0:
            return None
        
        random_lim = 5
        pic_info = None
        while not pic_info:
            random_lim -= 1
            if random_lim == 0:
                break
            pic_id = random.randint(1, self.cate_info.sequence)
            logger.debug('getting with{}:{}'.format(self.cate_info.id, pic_id))
            pic_info = self.db.get_pic(self.cate_info.id, pic_id)

        if pic_info: 
            self.db.pic_use_inc(self.cate_info.id, pic_id)

        return pic_info

    def random_pic_md5(self):
        pic_info = self.random_pic()
        if pic_info:
            return pic_info.md5
        return None
        

    def random_pic_path(self):
        pic_info = self.random_pic()
        if pic_info:
            file_name = '{}.{}'.format(pic_info.md5, pic_info.type)
            file_name = file_name.replace('/', 'SLASH') #avoid path revolving issue
            return os.path.join(self.cur_dir,file_name)
        return None

    def find_imgtype(self, type_str):
        prefix = 'image/'
        img_type = None
        index = type_str.find(prefix)
        if index == 0:
            img_type = type_str[len(prefix):]
        return img_type

    def save_pic(self, pic: PicObj):
        pictype = ''

        if pic.Url:
            try:
                res = httpx.get(pic.Url)
                res.raise_for_status()
                img_type = self.find_imgtype(res.headers['content-type'])
                if not img_type:
                    raise Exception('Failed to resolve image type')
                self.cate_info.sequence += 1;
                file_name = '{}.{}'.format(pic.Md5, img_type)
                file_name = file_name.replace('/', 'SLASH') #avoid path revolving issue
                file_path = os.path.join(self.cur_dir, file_name)
                logger.warning('Saving image to: {}'.format(file_path))
                with open(file_path, 'wb') as img:
                    img.write(res.content)
                self.db.add_pic(self.cate_info.id, self.cate_info.sequence, pic.Md5, img_type)
                self.db.set_cate(self.cate_info.id, self.cate_info.sequence)
                return True
            except Exception as e:
                logger.warning('Failed to get picture from url:{},{}'.format(pic.Url, e))
                raise
        
            return False

