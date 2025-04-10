import random
import re
import time
import requests
from config import pconf



def get_id_from_url(url):
    """从夸克网盘分享链接中提取分享ID
    Args:
        url: 分享链接，如 https://pan.quark.cn/s/3a1b2c3d
    Returns:
        str: 分享ID 密码 父目录？
    """
    url = url.replace("https://pan.quark.cn/s/", "")
    pattern = r"(\w+)(\?pwd=(\w+))?(#/list/share.*/(\w+))?"
    match = re.search(pattern, url)
    if match:
        pwd_id = match.group(1)
        passcode = match.group(3) if match.group(3) else ""
        pdir_fid = match.group(5) if match.group(5) else 0
        return pwd_id, passcode, pdir_fid
    else:
        return None


def generate_timestamp(length):
    """生成指定长度的时间戳
    Args:
        length: 需要的时间戳长度
    Returns:
        int: 指定长度的时间戳
    """
    timestamps = str(time.time() * 1000)
    return int(timestamps[0:length])


def ad_check(file_name: str) -> bool:
    """检查文件名是否包含广告关键词

    Args:
        file_name: 需要检查的文件名

    Returns:
        bool: True表示是广告文件，False表示不是广告文件
    """
    # 广告关键词列表
    # ad_keywords = [
    #     '广告', 'ad', '推广', '关注', '公众号', '小程序',
    #     '点击链接', '加群', 'QQ群', '微信群', '电报群',
    #     '免费资源', '获取更多', '更多资源',
    #     'readme', 'README', '说明', '必读',
    #     '打赏', '赞赏', '支付宝', '微信支付',
    #     '关注即可', '关注后', '关注公众号',
    #     '加入群', '入群', '资源来源网络，30分钟后删除，请及时保存'
    # ]

    ad_keywords = quark_config.get("ad_keywords")
    # ad_keywords = []

    # 将文件名转换为小写进行检查
    file_name_lower = file_name.lower()

    # 检查文件名是否包含广告关键词
    for keyword in ad_keywords:
        if keyword.lower() in file_name_lower:
            return True

    return False


import sqlite3
import logging

quark_config={}
class SqlLiteOperator:
    def __init__(self):
        self.conn = sqlite3.connect('./quark.db')
        self.cursor = self.conn.cursor()
        self.create_table()


    def create_table(self):

        # 文件转存记录
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS kan_files (
            file_id TEXT PRIMARY KEY,
            file_name TEXT,
            file_type INTEGER,
            share_link TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        self.conn.commit()

    def insert_files(self, file_id, file_name, file_type, share_link):
        """插入文件记录"""
        sql = 'INSERT OR REPLACE INTO kan_files (file_id, file_name, file_type, share_link) VALUES (?, ?, ?, ?)'
        try:
            self.cursor.execute(sql, (file_id, file_name, file_type, share_link))
            self.conn.commit()
            logging.debug(f"文件 {file_name} 记录已保存")
        except Exception as e:
            logging.error(f"保存文件记录失败: {e}")
            self.conn.rollback()

    # 删除文件
    def del_files(self, file_id):
        sql = '''
        delete from kan_files where file_id = ? 
        '''
        try:
            self.cursor.execute(sql, (file_id,))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()

    def find_share_link_by_name(self, file_name: str):
        """查询文件是否存在"""
        sql = '''
        SELECT share_link FROM kan_files WHERE file_name = ?
        '''
        self.cursor.execute(sql, (file_name,))
        share_link = self.cursor.fetchone()
        if share_link is None:
            return None
        else:
            return share_link[0]

    def find_expired_resources(self, expired_time: int):
        """查询失效资源
        Args:
            expired_time: 失效时间（分钟）
        """
        sql = '''
        SELECT a.* 
        FROM kan_files a 
        WHERE (strftime('%s', 'now') - strftime('%s', a.created_at))  > ? ;
        '''
        self.cursor.execute(sql, (expired_time * 60,))
        return self.cursor.fetchall()
    #
    # def __del__(self):
    #     """关闭数据库连接"""
    #     self.cursor.close()
    #     self.conn.close()

    def close_db(self):
        """关闭数据库连接"""
        self.cursor.close()
        self.conn.close()


class Quark:
    """夸克网盘操作类，用于自动化处理网盘文件"""

    def __init__(self) -> None:
        """初始化夸克网盘操作类
        """
        global quark_config
        quark_config = pconf("my")
        # 设置API请求头
        self.headers = {
            'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'accept': 'application/json, text/plain, */*',
            'content-type': 'application/json',
            'sec-ch-ua-mobile': '?0',
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'sec-ch-ua-platform': '"Windows"',
            'origin': 'https://pan.quark.cn',
            'sec-fetch-site': 'same-site',
            'sec-fetch-mode': 'cors',
            'sec-fetch-dest': 'empty',
            'referer': 'https://pan.quark.cn/',
            'accept-encoding': 'gzip, deflate, br',
            'accept-language': 'zh-CN,zh;q=0.9',
            'cookie': quark_config["quark_cookie"]
        }
        # 初始化数据库操作对象
        self.operator = SqlLiteOperator()
        # 存储目录ID，默认为None表示根目录
        res_save_dir = quark_config.get('quark_save_dir')
        if res_save_dir == '':
            self.parent_dir = None
        else:
            self.parent_dir = res_save_dir

    # 删除过期资源
    def del_expired_resources(self, expired_time):
        expired_list = self.operator.find_expired_resources(expired_time)

        # 遍历过期数据
        for expired_file in expired_list:
            fl = self.search_file(expired_file[1])
            # print(f"查询： {expired_file[1]}    ")
            # print(f"数量： {len(fl)}    ")
            # print(f"结果:  {fl}")
            # 网盘删除
            for f in fl:
                self.del_file(f.get("fid"))
                print(f'删除过期资源：{expired_file[1]}')
            # 数据库删除
            self.operator.del_files(expired_file[0])

    def store(self, url: str):
        """保存分享链接中的文件到自己的网盘
        Args:
            url: 分享链接
        """
        # 获取分享ID和token
        pwd_id, passcode, pdir_fid = get_id_from_url(url)
        is_sharing, stoken = self.get_stoken(pwd_id, passcode)
        detail = self.detail(pwd_id, stoken, pdir_fid)
        file_name = detail.get('title')

        # 检查文件是否已存在
        share_link = self.operator.find_share_link_by_name(file_name)
        file_not_exist = share_link is None
        if file_not_exist:
            first_id = detail.get("fid")
            share_fid_token = detail.get("share_fid_token")
            file_type = detail.get("file_type")

            # 设置保存目录
            other_args = {}
            if self.parent_dir is not None:
                other_args['to_pdir_fid'] = self.parent_dir

            # 保存文件并获取新的文件ID
            try:
                task = self.save_task_id(pwd_id, stoken, first_id, share_fid_token, **other_args)
                data = self.task(task)
                file_id = data.get("data").get("save_as").get("save_as_top_fids")[0]
            except Exception as e:
                # logging.error(f"转存-资源转存失败: {e}")
                raise

            # 如果是文件夹，检查并删除广告文件
            if not file_type:
                dir_file_list = self.get_dir_file(file_id)
                self.del_ad_file(dir_file_list)

            # 创建分享并获取新的分享链接
            try:
                share_task_id = self.share_task_id(file_id, file_name)
                share_id = self.task(share_task_id).get("data").get("share_id")
                share_link = self.get_share_link(share_id)
            except Exception as e:
                # logging.error(f"转存-资源分享失败: {e}")
                raise

                # 保存记录到数据库
            self.operator.insert_files(file_id, file_name, file_type, share_link)
        return file_not_exist, file_name, share_link

    def get_stoken(self, pwd_id: str, passcode=""):
        """获取分享文件的stoken
        Args:
            pwd_id: 分享ID
        Returns:
            str: stoken值
            :param passcode: 密码
        """
        url = f"https://drive-pc.quark.cn/1/clouddrive/share/sharepage/token"
        querystring = {"pr": "ucpro", "fr": "pc"}
        payload = {"pwd_id": pwd_id, "passcode": passcode}
        response = requests.post(url, json=payload, headers=self.headers).json()
        requests.post(url, json=payload, headers=self.headers, params=querystring).json()
        if response.get("status") == 200:
            return True, response["data"]["stoken"]
        else:
            return False, response["message"]

    def detail(self, pwd_id, stoken, pdir_fid, _fetch_share=0):
        """获取分享文件的详细信息
        Args:
            pwd_id: 分享ID
            stoken: 安全token
        Returns:
            dict: 文件详细信息
        """
        url = f"https://drive-pc.quark.cn/1/clouddrive/share/sharepage/detail"
        params = {
            "pr": "ucpro",
            "fr": "pc",
            "pwd_id": pwd_id,
            "stoken": stoken,
            "pdir_fid": pdir_fid,
            "force": "0",
            "_page": 1,
            "_size": "50",
            "_fetch_banner": "0",
            "_fetch_share": _fetch_share,
            "_fetch_total": "1",
            "_sort": "file_type:asc,updated_at:desc",
        }
        response = requests.request("GET", url=url, headers=self.headers, params=params)
        id_list = response.json().get("data").get("list")[0]
        if id_list:
            return {
                "title": id_list.get("file_name"),
                "file_type": id_list.get("file_type"),
                "fid": id_list.get("fid"),
                "pdir_fid": id_list.get("pdir_fid"),
                "share_fid_token": id_list.get("share_fid_token")
            }

    def save_task_id(self, pwd_id, stoken, first_id, share_fid_token, to_pdir_fid=0):
        """创建保存文件的任务
        Args:
            pwd_id: 分享ID
            stoken: 安全token
            first_id: 文件ID
            share_fid_token: 分享文件token
            to_pdir_fid: 目标文件夹ID，默认为0（根目录）
        Returns:
            str: 任务ID
        """
        logging.debug("获取保存文件的TASKID")
        url = "https://drive.quark.cn/1/clouddrive/share/sharepage/save"
        params = {
            "pr": "ucpro",
            "fr": "pc",
            "uc_param_str": "",
            "__dt": int(random.uniform(1, 5) * 60 * 1000),
            "__t": generate_timestamp(13),
        }
        data = {
            "fid_list": [first_id],
            "fid_token_list": [share_fid_token],
            "to_pdir_fid": to_pdir_fid,
            "pwd_id": pwd_id,
            "stoken": stoken,
            "pdir_fid": "0",
            "scene": "link"
        }
        response = requests.request("POST", url, json=data, headers=self.headers, params=params)
        logging.debug(response.json())
        return response.json().get('data').get('task_id')

    def task(self, task_id):
        """执行并监控任务状态
        Args:
            task_id: 任务ID
        Returns:
            dict: 任务执行结果
        """
        logging.debug("根据TASKID执行任务")
        while True:
            url = f"https://drive-pc.quark.cn/1/clouddrive/task?pr=ucpro&fr=pc&uc_param_str=&task_id={task_id}&retry_index={range}&__dt=21192&__t={generate_timestamp(13)}"
            response = requests.get(url, headers=self.headers).json()
            logging.debug(response)
            if response.get('status') != 200:
                raise Exception(f"请求失败，状态码：{response.get('status')}，消息：{response.get('message')}")  # 抛出异常
            # 状态码2表示任务完成
            if response.get('data').get('status') == 2:
                return response

    def share_task_id(self, file_id, file_name):
        """创建文件分享任务
        Args:
            file_id: 文件ID
            file_name: 文件名
        Returns:
            str: 分享任务ID
        """
        url = "https://drive-pc.quark.cn/1/clouddrive/share?pr=ucpro&fr=pc&uc_param_str="
        data = {
            "fid_list": [file_id],
            "title": file_name,
            "url_type": 1,  # 链接类型
            "expired_type": 1  # 过期类型
        }
        response = requests.request("POST", url=url, json=data, headers=self.headers)
        return response.json().get("data").get("task_id")

    def get_share_link(self, share_id):
        """获取分享链接
        Args:
            share_id: 分享ID
        Returns:
            str: 分享链接
        """
        url = "https://drive-pc.quark.cn/1/clouddrive/share/password?pr=ucpro&fr=pc&uc_param_str="
        data = {"share_id": share_id}
        response = requests.post(url=url, json=data, headers=self.headers)
        return response.json().get("data").get("share_url")

    def get_all_file(self):
        """获取网盘根目录下的所有文件
        Returns:
            list: 文件列表
        """
        logging.debug("正在获取所有文件")
        url = "https://drive-pc.quark.cn/1/clouddrive/file/sort?pr=ucpro&fr=pc&uc_param_str=&pdir_fid=0&_page=1&_size=50&_fetch_total=1&_fetch_sub_dirs=0&_sort=file_type:asc,updated_at:desc"
        response = requests.get(url, headers=self.headers)
        return response.json().get('data').get('list')

    def get_dir_file(self, dir_id) -> list:
        """获取指定文件夹下的所有文件
        Args:
            dir_id: 文件夹ID
        Returns:
            list: 文件列表
        """
        logging.debug("正在遍历父文件夹")
        url = f"https://drive-pc.quark.cn/1/clouddrive/file/sort?pr=ucpro&fr=pc&uc_param_str=&pdir_fid={dir_id}&_page=1&_size=50&_fetch_total=1&_fetch_sub_dirs=0&_sort=updated_at:desc"
        response = requests.get(url=url, headers=self.headers)
        return response.json().get('data').get('list')

    def del_file(self, file_id):
        """删除指定文件
        Args:
            file_id: 文件ID
        Returns:
            str/bool: 成功返回任务ID，失败返回False
        """
        logging.debug("正在删除文件")
        url = "https://drive-pc.quark.cn/1/clouddrive/file/delete?pr=ucpro&fr=pc&uc_param_str="
        data = {
            "action_type": 2,  # 删除操作类型
            "filelist": [file_id],
            "exclude_fids": []
        }
        response = requests.post(url=url, json=data, headers=self.headers)
        if response.status_code == 200:
            return response.json().get("data").get("task_id")
        return False

    def del_ad_file(self, file_list):
        """删除文件夹中的广告文件
        Args:
            file_list: 文件列表
        """
        logging.debug("删除可能存在广告的文件")
        for pre_file in file_list:
            file_name = pre_file.get("file_name")

            # 检查文件名是否包含广告关键词
            if ad_check(file_name):
                task_id = self.del_file(pre_file.get("fid"))
                self.del_file(task_id)

    def search_file(self, file_name):
        """搜索网盘中的文件
        Args:
            file_name: 文件名关键词
        Returns:
            list: 搜索结果列表
        """
        logging.debug("正在从网盘搜索文件🔍")
        url = "https://drive-pc.quark.cn/1/clouddrive/file/search?pr=ucpro&fr=pc&uc_param_str=&_page=1&_size=50&_fetch_total=1&_sort=file_type:desc,updated_at:desc&_is_hl=1"
        params = {"q": file_name}
        response = requests.get(url=url, headers=self.headers, params=params)
        return response.json().get('data').get('list')

    def mkdir(self, dir_path, pdir_fid="0"):
        """创建文件夹并返回文件id
        Args:
            dir_path: 创建文件名
            pdir_fid: 父文件id
        Returns:
            fid: 创建文件id
        """
        url = f"https://drive-pc.quark.cn/1/clouddrive/file"
        querystring = {"pr": "ucpro", "fr": "pc", "uc_param_str": ""}
        payload = {
            "pdir_fid": pdir_fid,
            "file_name": "",
            "dir_path": dir_path,
            "dir_init_lock": False,
        }
        response = requests.post(url=url, headers=self.headers, params=querystring, json=payload)
        return response.json().get('fid')


if __name__ == '__main__':
    quark = Quark()
    # quark.store('https://pan.quark.cn/s/21d7d1f50a5c?entry=sjss#/list/share')
    # quark.store('https://pan.quark.cn/s/37708b88d52e')
    file_list = quark.get_all_file()
    print(file_list)
    found_fid = next((f['fid'] for f in file_list if f['file_name'] == '临时资源'), None)
    quark.del_expired_resources(30)
