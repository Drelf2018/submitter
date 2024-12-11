<p align="center">
  <a href="https://github.com/Drelf2018/submitter/">
    <img src="https://user-images.githubusercontent.com/41439182/220989932-10aeb2f4-9526-4ec5-9991-b5960041be1f.png" height="200" alt="submitter">
  </a>
</p>

<div align="center">

# submitter

_✨ 基于 [webhook](https://github.com/Drelf2018/webhook) 的博文提交器 ✨_  

</div>

<p align="center">
  <a href="https://pypi.org/project/post-submitter/">下载</a>
  ·
  <a href="https://github.com/Drelf2018/submitter/blob/main/tests/ali.py">开始使用</a>
</p>

### 教程

下面这段代码是适配的我自己在阿里云上创建的 [webhook](https://github.com/Drelf2018/webhook) 实例。这个实例是通过扫描哔哩哔哩二维码来实现账户验证的，所以我们在创建账号时要先获取B站的验证链接，生成二维码。此时程序会通过输入暂停住，用手机扫码后稍等三秒再回车就可以通过验证了。`Token` 信息也会打印在屏幕上，可以保存在代码里，这样下次登录就不用账号密码了，例如 `@AliClient(ping=30, token=token)` 就不用再提供账号密码。其中这里的 `ping=30` 含义是每 `30` 秒向服务器报告一次自己在线，这样后续在网站上就可以看到自己的提交器是否还在正常工作，但是这个不是强制的，如果你不想报告自身状态，设置 `ping=-1` 这样的负数即可。

接下来就是提交器正式工作内容了，这里从 `submitter.adapter.weibo` 导入了适配器 `Weibo`，顾名思义就是将微博博文适配成 [webhook](https://github.com/Drelf2018/webhook) 规定的博文结构的工具。它的具体使用方法还请阅读源代码，非常简单易懂，通过阅读源码你也可以学习如何编写一个别的平台的适配器。后面我们从适配器中取出了第一个收集到的博文，并且发送至服务器用以测试任务 `Task`，这是 [webhook/model/user.go](https://github.com/Drelf2018/webhook/blob/ad577b5f93a67820545b2cddc2a999c6a352dd3e/model/user.go#L40) 中定义的一种请求结构，用来实现广播博文，也就是 `webhook` 的实现。

希望这个工具对你有用！

```py
from qrcode import QRCode

from submitter import Client, Task
from submitter.adapter.weibo import Weibo


class AliClient(Client):
    def __init__(self, uid: str = "", password: str = "", token: str = "", ping: float = -1):
        super().__init__("http://gin.web-framework-m88s.1990019364850918.cn-hangzhou.fc.devsapp.net", uid, password, token, ping)

    async def register(self) -> str:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0.0.0 Safari/537.36 Edg/116.0.1938.54",
            "Referer": "https://www.bilibili.com",
        }
        resp = await self.session.get("https://passport.bilibili.com/x/passport-login/web/qrcode/generate", headers=headers)
        result = resp.json()
        qr = QRCode(border=0)
        qr.add_data(result["data"]["url"])
        qr.make()
        qr.print_ascii()
        input("扫描二维码完成登录后按下回车继续注册")
        data = {
            "uid": self.uid,
            "password": self.password,
            "qrcode_key": result["data"]["qrcode_key"],
        }
        if await self.post("/register", json=data) == "success":
            return await self.token(self.uid, self.password)


@AliClient(uid="your_bilibili_uid", password="the_account_password_you_want_to_use_to_submit_blog")
async def main(self: AliClient):
    token = await self.register()
    self.log.info(f"Token[{token}]")
    # 注册完后就可以吧这个函数删了 用下面那个 注意用获取到的 Token 替换下面的空字符串

@AliClient(ping=30, token="")
async def ali(self: AliClient):
    async with Weibo(preload=["7198559139"]) as w:
        for mid in w.blogs:
            log = await self.test(
                blog=w.blogs[mid],
                task=Task(
                    public=True,
                    enable=True,
                    name="接收测试",
                    method="POST",
                    url="https://httpbin.org/post",
                    body="{{ json . }}",
                    README="接收所有微博",
                ),
            )
            self.log.info(log)
            break
```