import logging
import random
import re
import time
import requests

conf = {}


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

    global conf
    ad_keywords = conf.get("ad_keywords")
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

    def find_share_link_by_name(self, file_name: str):
        """查询文件是否存在"""
        sql = 'SELECT share_link FROM kan_files WHERE file_name = ?'
        self.cursor.execute(sql, (file_name,))
        share_link = self.cursor.fetchone()
        if share_link is None:
            return None
        else:
            return share_link[0]

    def __del__(self):
        """关闭数据库连接"""
        self.cursor.close()
        self.conn.close()

    def close_db(self):
        """关闭数据库连接"""
        self.cursor.close()
        self.conn.close()


class Quark:
    """夸克网盘操作类，用于自动化处理网盘文件"""

    def __init__(self, config) -> None:
        """初始化夸克网盘操作类
        Args:
            conf: 配置
        """
        global conf
        conf = config

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
            'cookie': conf.get("cookie")
        }
        # 初始化数据库操作对象
        self.operator = SqlLiteOperator()
        # 存储目录ID，默认为None表示根目录
        res_save_dir = conf.get('save_dir')
        if res_save_dir == '':
            self.parent_dir = None
        else:
            self.parent_dir = res_save_dir

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
        for file in file_list:
            file_name = file.get("file_name")

            # 检查文件名是否包含广告关键词
            if ad_check(file_name):
                task_id = self.del_file(file.get("fid"))
                self.task(task_id)

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
    # 使用示例
    # config = {
    #     "src_url": "ks.jizhi.me",
    #     "cookie1": "_UP_A4A_11_=wb965167905b4372a78e89ad55a748af; tfstk=fqGmGkigDxyXGyQ9mbVXadVbdK9-liN_xcCTX5EwUur5HoFt755ZXVFYQngtqlmt5olYkoUZj0E76ohxHAbjZDfOMn9j71VT_HKp9B3Xl5NwvSYNrDrb54ra5fw2wqN__3nCbt5KlDcYmlOg_UVzSP1a_1oaU4r75PS47s8ozuaa_sra7z7z5y74brlETarxbmGyJIoWJbojjb403L3441zSZr20Yqrh_1WUo-qEuuxd4f3LUVwi1N1gLqkIfyoV0hqsZ4lqLD-RHok3S2HiuI5zMjgqLRlefOo3ic2Eg8bNTqg4D74rTFBQ2bqxbj2yJ62TaXeUgYpWDRF0-cljmNfZY43KG8GMxgrsHyNzSfTFIl2N4CXPLz051z8tZO6_3zauA7aKeaw4tJRerUXEd-z7uBLkrO6_3zauvUYlLHw4PrRd.; _UP_F7E_8D_=0z44HdIBxZZqPa25Ub0TVXltLXQDyq1RwsMdKhXvERQvOk1AmQkNxLlLOSi3D%2FTTUCGf%2B5hDnkxLHpvA%2Fhicy1HUTu2LBlCPom4qTWeMFqCgN55FQx3lIyu%2B1OsWIKjG1w4pOGWcZjvuo4m2jHof9eRj66wpeTPO4r7NBD%2F4wEE0IpjIBHWretgcndtvmRjOjVn%2BnAjcaowXy52%2F9kbLMbzk4nczcPLP1rSgCMVm5ws2Z%2BPyTAVLm9UiDHFvPYOejtppHI1D5BWo9iWpC3nRSU7a6icULwkUypG1CzPKycsVOMEdD6uzZJXMxBnUatpyAHLu79tlMNqP8TGNMQXXgvSqK5ufzR58ZeivnehV0qE%2FWt1yDEDt%2BfWrmT4mVs6zZWXvqpzmoV3MeygIUCEakjmqUpi%2BMoCaK%2BK%2BYrCYUbg6F8u7yQFbh%2F0Q7RCSfK2U6tAXQttwc%2FtDK7HYGyvolg%3D%3D; _UP_D_=pc; __pus=481757cbfeebbb1d88612537ebeac5c1AATbouZ3q4A42xryvioZHiMLj1oA0B8rQCQAp+Wo1Y4DuOIWCQG+mRmcbHRzmsEmJuLDxXfbcUwJRoMYnyS3neQC; __kp=27e614c0-7a7f-11ef-87f7-f9e5c62a9c04; __kps=AATYIjLlcIEeoRU+aMylrVCd; __ktd=R9BUN0vqQ38VUloW/uHx9g==; __uid=AATYIjLlcIEeoRU+aMylrVCd; __puus=7b97a93c7fce17bf9f127762d5dfcfd6AATZByE6Qo9Tzb02mHpZVvp5HZWKrXDF2sjXr6caszU/7W0aUYNc9/ZLMQ4lBangoP/a5mynJ4uVgbwnf56weT9J/I67c2pL7tK9CAck9p3OXHZIWUXFfSYorssPynK4mM4bbVRxHncyQ/yoEFgUw0vINErPixpqcnhe58YM9ceUXaQyax31PLbx28+xG20e1onZOutSM87uWz84PHoABO12",
    #     "cookie": "b-user-id=d9fbd89a-7e69-ad5f-796c-f283169f7030; isg=BLKy4CoqAePk_z3fUL7Oas-FA_iUQ7bdscRo4nyL_mVQD1IJZNVQ7bts-6uzfy51; tfstk=f98oHci6V3S7FJqcim7SYZOce1mYF7_ChpUdpwBE0tWfpbOpTwzepBQRYYOpn9W2KkWEN653x19wvbGIEKcHeBadUTLd-MJOzMtRpTBh-B9iMA3tWQO5RZktBVnaHHBlR9ud8QbQVP_EBA3YDSSSewJRYRLQnIWft_yFUp740664Y9JFUiyVs1_F8wJFgI5Osk5U8gyqut1F89JF8jAT8OYelEkRXxjsNTCDo_jqDQW4LiTcZgXwaU4U855lqORPnAgotIS2OMYQOyjHah9C_LyrK9TDgU-wQxERUhfH6HArzr7JPQ-NYFkQYQQREZ8yjWzeiaXcvejbExXwPI81ui3ZsI8XeQTD9WuFMdB2NU7n7f_lzT7cGeHbz9x2YUI5R8khdEA2zHjPsorwM2aCgXL4AksPGsXTQdsG_HpeJkhmili54s1-Bjc0AksPGsXtijq_dg5fwAC..; _UP_A4A_11_=wb96c1edcce244058eef7b9a0b04541f; _UP_D_=pc; _UP_F7E_8D_=b0PSLv5dciNJR7POGgS3AJWwAsSGsVzdGUOU%2BWEa1%2FCQ9pt%2Flxcgspx%2F7jdZxm88%2BDZR%2F3OCavVVlSrlA%2FHE35guhUiWeFXSFrpiz7iQup7LB%2BL83Dn0lIDh36hnRcflW%2FQJYV4NNTtd2aHHLsro3PELcRKHSujuLbPeoOdhK0F%2B4CVxwd%2BA5kyclW53hcuTOm0qJXeruCsHvfOHRIiaNUy8%2FinnOmOa%2Bto1XMlORGQQCgydnJFD4oInCxl1g1C0s1YxLzJs52lWdoIk19nvWfytP81cJKxfv1GfwBTrR0bS%2FBGt91fGhZMwyZvOKbU%2F8ZkbgrGvmwxqzivluzXqQHrmHUwax9fVlczEGdRq2nJkSi56LgyDrXpsyYdGYA0F4Cj%2Fntr80vkUTca5E0LqLcBEt4UN6jDY; __pus=d4b4ba104bfbc7433c8e9235597ff76cAASDxWuXTR1OiVVovAdD9om4/GtkCTmTqugcP2jheBR9TGMkZPPKQsYQJhZaHxoAWu1+qkCX5bZtW5nFwq4KpwHi; __kp=b5377c00-c35a-11ef-996b-63e52b76dc2c; __kps=AAR4uAqdyWJqDmR/hvGc4/Ox; __ktd=6/QGUbqZLzTrYbWbzChb4g==; __uid=AAR4uAqdyWJqDmR/hvGc4/Ox; __puus=242c36535237a82908254c9bd4879722AASF8MU0hSGDuoLtbQ2dHfyu6bfgQ1awX3UeU377gqIXT/NI1XnUd7gkZIFZ4D3UsW86j089oqJjPmNfI453CfJRC2yyEBYqwGK76vlW4msLfGYvyql/cD1aRnLUXwFgUGiXlrWGmjuSZNyCPyNf5aJJKPNIsS0XWCLfLU4Ba+Vst9lgv4lDf7ST5+E8jbioI3HCDUCHMkdSTVYvW8SeUVnh",
    #     "save_dir": "17bd2d4dfbeb4ed9a7c2bde5bba73a15",
    #     "ad_keywords": [
    #     ]
    # }

    # 文件路径
    file_path = 'test.json'
    # 读取JSON文件
    with open(file_path, 'r', encoding='utf-8') as file:
        import json
        config = json.load(file)


    quark = Quark(config['My'])
    # quark.store('https://pan.quark.cn/s/21d7d1f50a5c?entry=sjss#/list/share')
    # quark.store('https://pan.quark.cn/s/37708b88d52e')
    file_list = quark.get_all_file()
    print(file_list)
    found_fid = next((f['fid'] for f in file_list if f['file_name'] == '临时资源'), None)

    if found_fid:
        print(f'已找到：{found_fid}')

        config['My']['save_dir_id'] = found_fid

        # 将修改后的数据写回JSON文件
        with open(file_path, 'w', encoding='utf-8') as file:
            json.dump(config, file, indent=4, ensure_ascii=False)
    else:
        print(f"未找到：{quark.mkdir('临时资源').json().get('fid')}")
