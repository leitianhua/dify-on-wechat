import time
import requests
import re
import random
import string
from typing import Any, Union, Tuple, List
from retrying import retry

# 常量定义
BASE_URL = "https://pan.baidu.com"
HEADERS = {
    'Host': 'pan.baidu.com',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
    'Sec-Fetch-Site': 'same-site',
    'Sec-Fetch-Mode': 'navigate',
    'Referer': 'https://pan.baidu.com',
    'Accept-Encoding': 'gzip, deflate, br',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8,en-US;q=0.7,en-GB;q=0.6,ru;q=0.5',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
}
CONFIG_PATH = "config.txt"
ICON_BASE64 = ""  # 如果需要图标，可以在这里定义
DELAY_SECONDS = 1
INVALID_CHARS = r'<>|*?\\:'
ERROR_CODES = {
    -1: '链接错误，链接失效或缺少提取码',
    -4: '转存失败，无效登录。请退出账号在其他地方的登录',
    -6: '转存失败，请用浏览器无痕模式获取 Cookie 后再试',
    -7: '转存失败，转存文件夹名有非法字符，不能包含 < > | * ? \\ :，请改正目录名后重试',
    -8: '转存失败，目录中已有同名文件或文件夹存在',
    -9: '链接错误，提取码错误',
    -10: '转存失败，容量不足',
    -12: '链接错误，提取码错误',
    -62: '转存失败，链接访问次数过多，请手动转存或稍后再试',
    0: '转存成功',
    2: '转存失败，目标目录不存在',
    4: '转存失败，目录中存在同名文件',
    12: '转存失败，转存文件数超过限制',
    20: '转存失败，容量不足',
    105: '链接错误，所访问的页面不存在',
    404: '转存失败，秒传无效',
}
EXP_MAP = {"1 天": "1", "7 天": "7", "30 天": "30", "永久": "0"}

# 预编译正则表达式
SHARE_ID_REGEX = re.compile(r'"shareid":(\d+?),"')
USER_ID_REGEX = re.compile(r'"share_uk":"(\d+?)","')
FS_ID_REGEX = re.compile(r'"fs_id":(\d+?),"')
SERVER_FILENAME_REGEX = re.compile(r'"server_filename":"(.+?)","')
ISDIR_REGEX = re.compile(r'"isdir":(\d+?),"')


class Baidu:
    """
    网络请求相关类。
    """

    def __init__(self, conf):
        self.s = requests.Session()
        self.baidu_config = conf
        HEADERS["Cookie"] = self.baidu_config["baidu_cookie"]
        self.headers = HEADERS
        self.bdstoken = ''

        requests.packages.urllib3.disable_warnings()

    @retry(stop_max_attempt_number=3, wait_random_min=1000, wait_random_max=2000)
    def get_bdstoken(self) -> Union[str, int]:
        url = f'{BASE_URL}/api/gettemplatevariable'
        params = {
            'clienttype': '0',
            'app_id': '38824127',
            'web': '1',
            'fields': '["bdstoken","token","uk","isdocuser","servertime"]'
        }
        r = self.s.get(url=url, params=params, headers=self.headers, timeout=10, allow_redirects=False, verify=False)
        if r.json()['errno'] != 0:
            return r.json()['errno']
        return r.json()['result']['bdstoken']

    @retry(stop_max_attempt_number=3, wait_random_min=1000, wait_random_max=2000)
    def get_dir_list(self, folder_name: str) -> Union[List[Any], int]:
        url = f'{BASE_URL}/api/list'
        params = {
            'order': 'time',
            'desc': '1',
            'showempty': '0',
            'web': '1',
            'page': '1',
            'num': '1000',
            'dir': folder_name,
            'bdstoken': self.bdstoken
        }
        r = self.s.get(url=url, params=params, headers=self.headers, timeout=15, allow_redirects=False, verify=False)
        if r.json()['errno'] != 0:
            return r.json()['errno']
        return r.json()['list']

    @retry(stop_max_attempt_number=3, wait_random_min=1000, wait_random_max=2000)
    def create_dir(self, folder_name: str) -> int:
        url = f'{BASE_URL}/api/create'
        params = {
            'a': 'commit',
            'bdstoken': self.bdstoken
        }
        data = {
            'path': folder_name,
            'isdir': '1',
            'block_list': '[]',
        }
        r = self.s.post(url=url, params=params, headers=self.headers, data=data, timeout=15, allow_redirects=False, verify=False)
        return r.json()['errno']

    @retry(stop_max_attempt_number=3, wait_random_min=1000, wait_random_max=2000)
    def verify_pass_code(self, link_url: str, pass_code: str) -> Union[str, int]:
        url = f'{BASE_URL}/share/verify'
        params = {
            'surl': link_url[25:48],
            'bdstoken': self.bdstoken,
            't': str(int(round(time.time() * 1000))),
            'channel': 'chunlei',
            'web': '1',
            'clienttype': '0'
        }
        data = {
            'pwd': pass_code,
            'vcode': '',
            'vcode_str': ''
        }
        r = self.s.post(url=url, params=params, headers=self.headers, data=data, timeout=10, allow_redirects=False, verify=False)
        if r.json()['errno'] != 0:
            return r.json()['errno']
        return r.json()['randsk']

    @retry(stop_max_attempt_number=3, wait_random_min=1000, wait_random_max=2000)
    def get_transfer_params(self, url: str) -> str:
        r = self.s.get(url=url, headers=self.headers, timeout=15, verify=False)
        return r.content.decode("utf-8")

    @retry(stop_max_attempt_number=5, wait_random_min=1000, wait_random_max=2000)
    def transfer_file(self, params_list: List[str], folder_name: str) -> (int, int):
        url = f'{BASE_URL}/share/transfer'
        params = {
            'shareid': params_list[0],
            'from': params_list[1],
            'bdstoken': self.bdstoken,
            'channel': 'chunlei',
            'web': '1',
            'clienttype': '0'
        }
        data = {
            'fsidlist': f"[{','.join(params_list[2])}]",
            'path': f'/{folder_name}'
        }
        r = self.s.post(url=url, params=params, headers=self.headers, data=data, timeout=30, allow_redirects=False, verify=False)
        errno = r.json()['errno']
        new_fid = ""
        if errno == 0:
            new_fid = r.json()["info"][0]["fsid"]
        elif errno == 4:
            new_fid = r.json()["duplicated"]["list"][0]["fs_id"]
        else:
            print(f"transfer_file:{r.json()}")
        return r.json()['errno'], new_fid

    @retry(stop_max_attempt_number=3, wait_random_min=1000, wait_random_max=2000)
    def create_share(self, fs_id: int, expiry: str, password: str) -> Union[str, int]:
        url = f'{BASE_URL}/share/set'
        params = {
            'channel': 'chunlei',
            'bdstoken': self.bdstoken,
            'clienttype': '0',
            'app_id': '250528',
            'web': '1'
        }
        data = {
            'period': expiry,
            'pwd': password,
            'eflag_disable': 'true',
            'channel_list': '[]',
            'schannel': '4',
            'fid_list': f'[{fs_id}]'
        }
        r = self.s.post(url=url, params=params, headers=self.headers, data=data, timeout=15, allow_redirects=False, verify=False)
        if r.json()['errno'] != 0:
            return r.json()['errno']
        return r.json()['link']

    def store(self, link_code: str):
        folder_name = self.baidu_config["baidu_save_dir"]
        self.bdstoken = self.get_bdstoken()
        if isinstance(self.bdstoken, int):
            print(f"获取bdstoken失败，错误代码：{ERROR_CODES.get(self.bdstoken)}")
            return
        # 预处理链接至标准格式。
        normalized_link = normalize_link(link_code)
        # 提取 URL和提取码
        url, password = parse_url_and_code(normalized_link)

        # 验证提取码
        bdclnd = self.verify_pass_code(url, password)
        print(f"bdclnd:{bdclnd}")
        if isinstance(bdclnd, int):
            print(f"验证提取码失败，错误代码：{ERROR_CODES.get(bdclnd)}")
            return

        self.headers["Cookie"] = update_cookie(bdclnd, self.headers["Cookie"])

        # 获取转存参数
        response = self.get_transfer_params(url)
        params = parse_response(response)
        print(f"params:{params}")
        if isinstance(params, int):
            print(f"获取转存参数失败，错误代码：{ERROR_CODES.get(params)}")
            return

        # 创建目标目录
        if folder_name:
            result = self.get_dir_list(f"/{folder_name}")
            if isinstance(result, int):
                result = self.create_dir(folder_name)
                if result != 0:
                    print(f"创建目录失败，错误代码：{ERROR_CODES.get(result)}")
                    return

        # 执行转存
        result, nwe_fid = self.transfer_file(params, folder_name)
        if result == 0:
            print(f"转存成功：{normalized_link}")
        elif result == 4:
            print(f"资源已存在：{normalized_link}")
        else:
            print(f"转存失败，错误代码：{ERROR_CODES.get(result)}")
            return

        # 分享文件
        expiry = "1 天"
        password = generate_code()
        share_result = self.create_share(nwe_fid, EXP_MAP[expiry], password)
        if isinstance(share_result, str):
            print(f"分享成功：{share_result}?pwd={password}")
        else:
            print(f"分享失败，错误代码：{share_result}")


def normalize_link(url_code: str) -> str:
    normalized = url_code.replace("share/init?surl=", "s/1")
    normalized = re.sub(r'[?&]pwd=', ' ', normalized)
    normalized = re.sub(r'提取码*[：:]', ' ', normalized)
    normalized = re.sub(r'^.*?(https?://)', 'https://', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized


def parse_url_and_code(url_code: str) -> Tuple[str, str]:
    url, code = map(str.strip, url_code.split(' ', 1))
    return url[:47], code[-4:]


def parse_response(response: str) -> Union[List[str], int]:
    shareid_list = SHARE_ID_REGEX.findall(response)
    user_id_list = USER_ID_REGEX.findall(response)
    fs_id_list = FS_ID_REGEX.findall(response)
    server_filename_list = SERVER_FILENAME_REGEX.findall(response)
    isdir_list = ISDIR_REGEX.findall(response)
    if not all([shareid_list, user_id_list, fs_id_list, server_filename_list, isdir_list]):
        return -1
    return [shareid_list[0], user_id_list[0], fs_id_list, list(dict.fromkeys(server_filename_list)), isdir_list]


def update_cookie(bdclnd: str, cookie: str) -> str:
    cookies_dict = dict(map(lambda item: item.split('=', 1), filter(None, cookie.split(';'))))
    cookies_dict['BDCLND'] = bdclnd
    updated_cookie = ';'.join([f'{key}={value}' for key, value in cookies_dict.items()])
    return updated_cookie


def generate_code() -> str:
    characters = string.ascii_letters + string.digits
    code = ''.join(random.choice(characters) for _ in range(4))
    return code

if __name__ == '__main__':
    config = {
        "baidu_cookie": "BAIDUID=F7471EA7D63A8162C152D8E91452CD2F:SL=0:NR=10:FG=1;Hm_lvt_7a3960b6f067eb0085b7f96ff5e660b0=1721109275;Hm_lvt_fa0277816200010a74ab7d2895df481b=1721110930;secu=1;PANWEB=1;BIDUPSID=F7471EA7D63A8162C152D8E91452CD2F;PSTM=1727401942;BDUSS=0NaalBXOH51eUNQVDFVWW5uVlFocEQ4VjBrOE40OEZjSVFiMk94UndWek1UMWxuRVFBQUFBJCQAAAAAAAAAAAEAAACjq02mx-vOwsjzyOfT8TcAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAMzCMWfMwjFnY;BDUSS_BFESS=0NaalBXOH51eUNQVDFVWW5uVlFocEQ4VjBrOE40OEZjSVFiMk94UndWek1UMWxuRVFBQUFBJCQAAAAAAAAAAAEAAACjq02mx-vOwsjzyOfT8TcAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAMzCMWfMwjFnY;MCITY=-236%3A;csrfToken=3MbjVOqtYyp3U6sByY5fn5WG;STOKEN=530ff110132975b8b53d7c1a860a4ab5775c0442d8ee3c6dd1619db83f3e24e4;BDCLND=99%2FH%2BUQgVGaCVTzLSYZpYHAi56hRwyPPJdgNyVJyKoU%3D;Hm_lvt_182d6d59474cf78db37e0b2248640ea5=1739410760;HMACCOUNT=11C83CEB9BB197E9;Hm_lpvt_182d6d59474cf78db37e0b2248640ea5=1739410761;delPer=0;BAIDUID_BFESS=F7471EA7D63A8162C152D8E91452CD2F:SL=0:NR=10:FG=1;ZFY=TFJ7c7KPh02lkCSxU8RJfRk8ZiKgDitAe7ACVEmfnK4:C;BDRCVFR[bPTzwF-RsLY]=mk3SLVN4HKm;H_WISE_SIDS=110085_633618_640399_640445_638942_638943_638938_641044_641048_641124_641113_641120_641121_641117_641188_641193_641190_641320_640864;H_WISE_SIDS_BFESS=110085_633618_640399_640445_638942_638943_638938_641044_641048_641124_641113_641120_641121_641117_641188_641193_641190_641320_640864;RT='z=1&dm=baidu.com&si=6f9cdd5e-8db4-4114-a341-444102bcc38b&ss=m74g5vff&sl=2&tt=44g&bcn=https%3A%2F%2Ffclog.baidu.com%2Flog%2Fweirwood%3Ftype%3Dperf&ld=esz&ul=2t9m&hd=2t9u';PSINO=7;ab_sr=1.0.1_MDc2ZmY4ODVmMDgzNzA3YTQ5ZDgwYWJlZjM2MGJlMGEwNDUzNDU2YzQ5NTNhODhjNDlhNmFkYzIyY2YzMzE3MGQ3N2Y5MGVhZWY5YjAwMDNiZjg3NTNjZjAyOTI0NTY3NmM3MTdhNWZjZjk5MGUzZGNkMWRmNmQwMWNhZTc5YmYwMzY4ZjFkYTgxZTkyNDUzOGQ1MDhiZTY2YmY4NjMzZWM5MjAxYjI4YWViYWJlMjQ2NDI3NWY2NzMwMDA3ZGNk;H_PS_PSSID=60277_61027_61987_62079_62056_62062_62108_62105_62102_62097_62114_62129_62150_62168_62175_62185_62187_62183_62195;BA_HECTOR=8k0ka40h0l8085al0ka120ahai0cl91jr2m471u;newlogin=1;PANPSC=10638805093916495741%3A%2BZFtqHi72o44nrdX73eyLlcS2d9ns3O5g0mIZdLHpdQGbqupDlB1gnNc1x6dU266RqSmmesmlWviLaLUl0KD5De4ZdaW7CoOlL98c8Ccr9ch6uZoP3DwQ9YfJggg9xZJMXXf2cBzuU%2Fzuvycj6b93pk6Ed%2FLbXhwaB0vkxhGatPcHTlqoT8xMYl2TA8TQL280aE2XxeeBEaos0HeUwfyEomr8AGB15NuQSOxR8B%2BrGNfneKGBG%2FiLZ5m71rmiKJ0;ndut_fmt=72B71E6B07EE4F807588FE3FC0E92EB9DF4F3DE9DDF240AF8E0E370B72492648",
        "baidu_save_dir": "临时资源目录",
    }
    baidu= Baidu(config)
    baidu.store("https://pan.baidu.com/share/init?surl=6EEUs-mMcI6fT56-uXBZJw&pwd=8888")