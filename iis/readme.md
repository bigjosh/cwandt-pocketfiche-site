# IIS set up

This is the setup for a couple of host python scripts that...

1. Let admin users generate upload URLs for backers to upload their parcel images
2. Let backers with generated update URLs upload their parcel images and pick what location they want on the grid.

# Set up

## IIS


Enable IIS + CGI
Control Panel -> Turn Windows features on or off -> check Internet Information Services and under Application Development Features check CGI. 

Install Python (3.x).

Find python.exe with "where python" in a command prompt.

Add a /cgi-bin virtual directory and map *.py to Python:
IIS Manager -> your site -> Handler Mappings -> Add Script Map  

Request path: *.py

Executable: C:\Python312\python.exe -u "%s"

Access: Script.
Place scripts in C:\inetpub\cgi-bin\. 

Test script: C:\inetpub\cgi-bin\hello.py

```
import cgi
name = cgi.FieldStorage().getfirst("name","world")
print("Content-Type: text/plain; charset=utf-8"); print()
print(f"hello {name}")
```

Browse: http://localhost/cgi-bin/hello.py?name=you

2. Install Python
3. Install the python scripts

