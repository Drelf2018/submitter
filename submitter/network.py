from typing import Any, List, Optional, Tuple

import httpx

from .data import Post, parse

HEADERS = {
    "Connection": "keep-alive",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Upgrade-Insecure-Requests": "1",
    "User-Agent": "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.62 Safari/537.36",
}


class ApiException(Exception):
    """
    接口访问错误
    """
    def __init__(self, code: int, message: str, **kwargs):
        super().__init__(message)
        self.code = code
        self.message = message
        self.kwargs = kwargs

    def __str__(self):
        return f"({self.code}, {self.message})"


class Session:
    """
    会话类
    
    基于 `httpx.AsyncClient`

    参考 `golang` 中错误处理方式
    """
    def __init__(self, url: str, headers: Optional[dict] = None) -> None:
        """
        Args:
            url: 基础接口地址
        
            headers: 自定义请求头
        """
        self.__session = httpx.AsyncClient(base_url=url)
        if headers is None:
            self.headers = HEADERS.copy()
        else:
            self.headers = headers

    async def request(
        self,
        method: str,
        url: str,
        headers: Optional[dict] = None,
        *args,
        **kwargs
    ) -> Tuple[Any, Optional[Exception | ApiException]]:
        # prepare
        if headers is None:
            headers = self.headers
        # fetch
        try:
            resp = await self.__session.request(method, url, headers=headers, *args, **kwargs)
            assert resp.status_code == 200, f"<Response [{resp.status_code}]>"
            result = resp.json()
        except Exception as e:
            return None, e
        # data
        if result["code"] != 0:
            return None, ApiException(**result)
        return result["data"], None

    async def get(self, url: str, headers: Optional[dict] = None, *args, **kwargs):
        return await self.request("GET", url, headers, *args, **kwargs)
    
    async def post(self, url: str, headers: Optional[dict] = None, *args, **kwargs):
        return await self.request("POST", url, headers, *args, **kwargs)
    
    async def must_get(self, url: str, headers: Optional[dict] = None, *args, **kwargs):
        data, _ = self.get(url, headers, *args, **kwargs)
        return data
    
    async def must_post(self, url: str, headers: Optional[dict] = None, *args, **kwargs):
        data, _ = self.post(url, headers, *args, **kwargs)
        return data
    

class Api(Session):
    """
    Api 实现层
    """
    def __init__(self, url: str, token: str = ""):
        """
        Args:
            url: 基础接口地址
        
            token: 鉴权码
        """
        Session.__init__(self, url, {"Authorization": token})

    async def register(self, auth: str):
        """
        注册或获取鉴权码
        """
        return await self.get("/register", headers={"Authorization": auth})

    async def submit(self, post: Post):
        """
        提交博文
        """
        _, err = await self.post("/submit", data=post.json)
        return err
    
    async def posts(self, begin: int = None, end: int = None) -> List[Post]:
        """
        查询博文
        """
        params = {}
        if begin is not None:
            params["begin"] = begin
        if end is not None:
            params["end"] = end
        resp, err = await self.get("/posts", params=params)
        if err is not None:
            return []
        return [parse(v) for v in resp["posts"]]
