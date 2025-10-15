# C:\inetpub\cgi-bin\hello.py
import cgi
name = cgi.FieldStorage().getfirst("name","world")
print("Content-Type: text/plain; charset=utf-8"); print()
print(f"hello {name}")
