# BPLab Trace V4.4 Clean GitHub Package

大连标普实验室样品全过程追溯系统

本包已经重新制作。ZIP内部目录和文件名全部使用英文字符，避免在Windows、macOS、GitHub或Streamlit之间出现中文文件名乱码；系统页面、客户信息、样品名称和记录内容仍正常显示中文。

## 已修复

- 删除旧包内已经乱码的模板文件名。
- 全部程序源代码统一为UTF-8。
- 全部SOP和原始记录表改用稳定英文文件名。
- 重新绑定程序中的模板路径。
- 使用最新上传的裂纹萌生、翘曲、耐急冷急热、厚度测量文件。
- 不携带旧数据库，首次运行自动生成干净数据库。

## 上传GitHub

解压后，将文件夹中的全部内容上传到仓库根目录。仓库根目录应直接看到 app.py、constants.py、templates 和 requirements.txt。Streamlit入口选择 app.py。

## 演示账号

管理员：admin / admin123
收样员：receiver / receive123
实验员：tester / test123
复核员：reviewer / review123
样品管理员：store / store123
