import setuptools

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

with open("requirements.txt", "r", encoding="utf-8") as f:
    requires = f.read()

try:
    with open("github.txt", "r", encoding="utf-8") as f:
        cfg = f.read().split("|")
except:
    cfg = ["v0.0.0"]

# python setup.py develop
setuptools.setup(
    name="post_submitter",
    version=cfg[0],
    license="MIT",
    author="Drelf2018",
    author_email="drelf2018@outlook.com",
    description="基于 webhook 的博文提交器",
    long_description_content_type="text/markdown",
    long_description=long_description,
    packages=setuptools.find_packages(),
    install_requires=requires.splitlines(),
    keywords=["python", "weibo", "webhook"],
    classifiers=[
        "Development Status :: 1 - Planning",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Operating System :: Unix",
        "Operating System :: MacOS :: MacOS X",
        "Operating System :: Microsoft :: Windows",
    ],
    url="https://github.com/Drelf2018/submitter",
    python_requires=">=3.8",
)
