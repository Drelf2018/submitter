import asyncio
import os
import re

from submitter import Blog, generate_blog_image
from submitter.adapter import Weibo

min_options = """
[description]
enable = false

[time]
icon = false
hoisting = true

[avatar]
enable = false

[banner]
enable = false
"""

brief_options = """
[description]
enable = false

[time]
icon = false
hoisting = true
"""

max_options = """
[banner.image]
enable = true
ratio = 1.78

[uid]
enable = true

[follow]
extra_primary = "{.submitter}"
extra_secondary = "信源"

[footer]
enable = true
"""


def prepare(blog: Blog):
    if blog.platform == "weibo" and blog.type == "blog":
        blog.banner = [re.sub(r"crop\.\d+\.\d+\.\d+\.\d+\.\d+", "crop.0.0.0.0.0", b) for b in blog.banner]
    if blog.reply is not None:
        prepare(blog.reply)


async def main():
    if not os.path.exists("img"):
        os.mkdir("img")
    async with Weibo(preload="7198559139") as w:
        blog = w.blogs["5095712087868362"]
        prepare(blog)

        blog.extra = {"generate_options": min_options}
        img = await generate_blog_image(blog)
        img.save(f"./img/min.jpg")

        blog.extra = {"generate_options": brief_options}
        img = await generate_blog_image(blog)
        img.save(f"./img/brief.jpg")

        blog.extra = {"generate_options": ""}
        blog.edited = True
        img = await generate_blog_image(blog)
        img.save(f"./img/default.jpg")

        blog.extra = {"generate_options": max_options}
        img = await generate_blog_image(blog)
        img.save(f"./img/max.jpg")


asyncio.run(main())
