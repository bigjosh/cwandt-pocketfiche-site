# Pocket Fische upload system

This system lets backers upload thier images and pick where on the world they want to place them. It also lets admins authorize backers. 

It is opnionated in that you only get once chance to put your image into the world. Once you do that, yopu can not update it. This is hopefully to encourage people to start uploading thier content sooner to get the ball rolling.  If we let people update thier images then they would be incentived to upload place holder just to secure a good location and the world would look crappy. 

I want to avoid any databases or complexity, so everything is stored in files in a data folder that *must* be outside of the app folder for security so there is no chance that the server will serve the data files. 

Also in the name of simplicity, I picked the built-in python webserver's cgi-bin mode as the platorm. Flask is just too much complexity for this project. 

# Quick start

## Set up

1. Clone this repo
2. Create a data folder outside of the app folder. MUST BE OUTSIDE OF THE PATH OF THIS REPO
3. Set an environment variable called `DATA_DIR` to the path of the data folder. In windows, you can do this by running `setx DATA_DIR=C:\path\to\data` in the command prompt.
4. From the root of this repo, run...
    ```
     python -m http.server --cgi
    ```
5. Open http://localhost:8000 and you should see a not authoized page.
6. If you want HTTPS, set up another web server (like IIS) to forward to this port.

## Add admin users

Make one file for each admin user in the data/admins folder. The file should be named {admin-id}.txt and should contain the name of the person on the first line and the notes on the second line. Pick a hard to guess names for these files, like 8 random uppercase letters. Do not tell it to anyone - this is basically that admin's password.


# High level flow

1. An admin visits the admin page and enters a backer-id and we generate a unique access code for that backer. 
2. Admin sends a URL to backer that includes the access code.
3. Backer visits the URL and is asked to upload thier image. They also specify the parcel location they want to place the image. We remind them that the image must be 500x500x1 PNG.
4. Backer uploads image with a POST. The POST also has the access code and parcel location.
5. Server checks the image and location to make sure they are valid. If not, it returns an error message.
6. Server checks if that access code has already successfully uploaded an image. If it has, it returns an error message.
7. Server checks if the location is already claimed. If it is, it returns an error message.
8. Server saves the image to the data directory.
9. Server returns a success message.

## Behind the scenes. 

App Files-

```
style.css
admin.html
upload.html
cgi-bin/app.py    
```

The `admin.html` and `upload.html` are static webpages that are served by the python webserver.  They include the `style.css`. We give html elements IDs so we can style them in the CSS.

There is one app processor called `cgi-bin/app.py` that is a cgi-script. It is called by static webpages.

The app page always gets at least a `command` parameter. Some commands also expect additional parameters in the POST. 

All admin commands require an `admin-id` parameter.
All backer commands require an `code` parameter.

### the static webpages

All links in the static webpages should have "no-referrer" set in the referrer policy to avoid leaking the access code in the URL.

#### `admin.html`

A simple form with fields for "backer-id" and "notes". It submits a POST with those fields to the app processor with the `command` parameter set to `generate-code` and the `admin-id` parameter from the URL. The POST also has the `backer-id` and `notes` parameters. 

If the POST is successful, it shows a page with the specified backer-id and the URL to the `upload.html` page with the `code` parameter from the POST. It has a button to copy the URL to the clipboard.

#### `upload.html`

This is where all of the action with backers happens.

We show an upload form which collects the image they want to upload, a field for the parcel-location to place the image. 

They can drag and drop an image or select it from their file system. 

Once they do that, the page has JS that processes the image into a 500x500x1 PNG and shows it to user as a preview. They can try again if they don't like it. 

Next is the parcel-location field which can take a location from "A1" to "AL38".

Finally there is an "Upload image " submit button that makes a POST to the app processor with the `command` parameter set to `upload`, the `parcel-location` parameter from the form, and the `code` parameter from the URL, and the image in the POST data. 

If the POST is successful, the page says "You have successfully uploaded your image! Here is the link to your image...." and displays a link based on the returned parcel-location.  

If the POST fails, the page indicates the reason and keeps the preview image and previewously requested parcel-location so they can try again after making changes. 

### the app processor

The app processor is a cgi-script that is called by the static webpages.

All calls to the cgi-script must have a `command` parameter. Some commands also expect additional parameters in the POST. 

#### return values

If the request failed due to something in the request like bad auth or incorrect image size etc, then we return an http error code. 

If the request failed due to something in the server state like a taken location or a used code, then we return a JSON object with a `status` field set to `error` and a `message` field set to the error message. 

If the request was successful, then we return a JSON object with a `status` field set to `success` and potentially other fields depending on the command. 

#### data handling

All data is stored in the data directory, which the app locates using the `DATA_DIR` environment variable. It should be *outside* the app directory tree for securuty since it has secrets in it. 

Any time we "atomic-add" a file to the data directory, we first create the file as a temp file in the target directory and then "move" it to the final name. If the move fails, we delete the temp file and handle the error. This is to prevent a race condition where the file already exists or another process might try to create the same file or access the file before it is fully written. 

The data directory has the following structure:

```
data/
    admins/ - one file per admin. The name of the file is `{admin-id}.txt` and the contents of the file are the name
     of the admin and the notes separated by a newline.
    access/ - one file per access code. The name of the file is `{code}.txt` and the contents of the file are 
    the backer-id and the notes separated by a newline. 
    locations/ - one file per access code. The name of the file is `{code}.txt` and the contents of the file are 
    the parcel-location. If the code is here, then the user has already successfully uploaded an image.
    parcels/ - one file per parcel. The name of the file is the `{parcel-location}.png` and the contents of the file are the parcel-image.
```

#### Admin commands

The admin commands are protected by needing a valid admin-id in the `admin-id` parameter. The admin commands will check if the admin-id exists as a file in the data/admins directory and if it does not then we return a "not autorized" error. 

##### command=`generate-code`.

Checks for autorization as described above. 

This command generates a new access code for a backer. It takes a POST with the `backer-id` and `notes` parameters. 

To generate the code, we generate a true random string of 8 uppercase characters. We then "atomic-add" a file in the data directory named `access/{code}.txt` where `code` is the code, and the contents of the file are the backer-id and the notes separated by a newline. 

If the "atomic-add" succeeds, we return json `{'status': 'success', 'code': code}`.

If the "atomic-add" fails, we return json `{'status': 'error', 'message': 'code already exists'}`.

#### backer commands

##### command=`upload`.

This command handles the upload of a parcel image. It takes a POST with the `code` and `parcel-location` parameters and the image in the POST data. 

1. check the code exists in the `access/` dir and if not returns a "401: not autorized" error. 
2. check if the parcel location is valid. If it is not, we return a "400: Invalid location" error. 
3. check if the image is a 500x500x1 PNG. If not, we return a "406: Invalid image" error.
4. atomic-add a new file `locations/{code}.txt`. The file new contents are the requested parcel-location. If this fails, we return the error as JSON `{'status': 'used', 'location': existing location}` where existing location is the location that was in the existing file that blocked us from doing the atomic-add.
5. "atomic-add" the uploaded image file to the `parcels/` dir as {parcel-location}.png`. If this fails, we return JSON `{ status: 'taken', location: existing location}` and delete the `locations/{code}.txt` file we created in the step above.
6. If we get here, the image upload was successful. We return the parcel-location as JSON `{ status: 'success', location: parcel-location}`.
