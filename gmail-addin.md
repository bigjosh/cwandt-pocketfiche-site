# Overview

This documents the gmail add-in that makes it possible to create upload URLs from directly inside the gmail web version.

It uses the existing server API (see `/upload-server/app.py`) to generate the new upload URL.

# UI

We add a new app script compose trigger that creates a card with visible/fillable fields for..

`ADMIN-ID` : The secret ID for this pocket fisce user. 
`NOTES`    : Free for notes.
`BACKER-ID`: Preinitialized with the recipient email address. 

These fields mirror the same named fields in the pocket fische admin page. The fields remember their last value across instances for this user.

Additionally there is a submit button called "Insert URL". 

# Functionality

Pushing the "Insert URL" button generates a REST request to the pocket fiche server API using the `generate-code` command. The base URL of the server is https://pf.josh.com/upload/cgi-bin/app.py` and parameters as follows...

`COMMAND` : `generate-code`

`ADMIN-ID` and `NOTES` from the current values in the add-in panel. 

`BACKER-ID` is set to the current destination address of the currently active draft email.

When the REST call returns, the add-in uses the returned `code` to create an upload URL in the form `https://pf.josh.com/upload/upload.html?code={code}` and then pastes the upload URL at the current cursor location in the draft email. 

# Distribution

This is distributed as an unpublished plug0in. This avoids all the overhead of needing google approval, but it does mean that every user must also be an editor on the appscript project and also means a slightly harder install procedure. 
