# Gmail Add-in Installation

## Create the Project

1. Go to [script.google.com](https://script.google.com) and click **New project**
2. Rename the project to "Pocket Fiche URL Generator" (click "Untitled project" at top)

## Add the Code

3. The editor opens with a default `Code.gs` file — replace its contents with the contents of `Code.gs` from this folder (Note that the only way I could find to do this is to copy/paste - drag/drop doesn't work)
4. Click the **gear icon** (Project Settings) in the left sidebar
5. Check **"Show 'appsscript.json' manifest file in editor"**
6. Go back to the **Editor** (code icon `< >` in the left sidebar)
7. Click `appsscript.json` in the file list and replace its contents with the contents of `appsscript.json` from this folder

## Install for Yourself

8. Click **Deploy** > **Test deployments**
9. Under **Gmail**, click **Install**
10. Grant the requested permissions (you'll see an "unverified app" warning — click Advanced > Go to Pocket Fiche URL Generator)

## Add Other Users

11. Click **Share** (top right) and add each user as an **Editor**
12. Each user opens the project URL with the embeded "OPEN" button, then does **Deploy** > **Test deployments** > **Install**

## Usage

1. Open Gmail and compose a new email (or reply to one)
2. Fill in the **TO** field with the backer's email address
3. In the compose sidebar on the right, click the **Pocket Fiche** icon
4. Enter your **ADMIN-ID** and optional **NOTES**
5. Confirm the displayed TO recipient is correct
6. Click **Insert URL** — the upload link is inserted at your cursor
