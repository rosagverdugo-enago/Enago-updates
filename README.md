# Enago Assignment Watcher

Checks hub.enago.com/experts every 5 minutes from GitHub's free cloud
runners and pushes an instant notification to your phone and Mac when a
new assignment appears. No computer of yours needs to stay on.

## How it works

- A GitHub Actions workflow runs `check_assignments.py` on a schedule.
- The script logs into the portal, reads the current assignment list, and
  compares it to `seen_assignments.json` (the list from last time).
- Anything new triggers a push notification via **ntfy.io** (free, no
  account needed) straight to your phone and Mac.
- The workflow commits the updated `seen_assignments.json` back to the repo
  so the next run knows what's already been seen.

## One-time setup (about 15-20 minutes)

### 1. Get notifications on your phone and Mac
- Install the **ntfy** app: [App Store](https://apps.apple.com/app/ntfy/id1625396347) (iOS) or [Play Store](https://play.google.com/store/apps/details?id=io.heckel.ntfy) (Android), and the **ntfy desktop app** or just use [ntfy.sh](https://ntfy.sh) in a Mac browser tab.
- In the app, "subscribe" to a topic name of your choosing - make it long and random since anyone who knows the topic name can see your notifications, e.g. `enago-assignments-x7k2m9`.
- That topic name is what you'll put in the `NTFY_TOPIC` secret below.

### 2. Create a GitHub repo
- Create a new **private** repository on GitHub.
- Upload all the files from this folder, preserving the `.github/workflows/` folder structure.

### 3. Add your credentials as secrets
In the repo: Settings -> Secrets and variables -> Actions -> New repository secret. Add:
- `ENAGO_EMAIL` - your Enago login email
- `ENAGO_PASSWORD` - your Enago login password
- `NTFY_TOPIC` - the topic name you picked in step 1

These are encrypted and never appear in logs or code.

### 4. Parsing is already set up - but confirm the login form fields
The assignment-parsing logic is done: it looks for the "New ASN" table by
its column headers (ASN Code, Service, Subject Area, etc.) and checks for
the literal text "No Assignment Found" to know whether anything's posted.

The one thing still unverified is the **login form's field names** (what
the `<input>` for email/password are actually called in the HTML), since
that's on a different page than the screenshot you showed me. On a Mac:
1. Go to the login page in Chrome or Safari.
2. Right-click the email field -> **Inspect**.
3. Look for `name="..."` on the `<input>` tag (e.g. `name="login"` or
   `name="email"`).
4. Open `check_assignments.py`, find the `LOGIN FORM` section near the top
   of `log_in()`, and make sure the `payload` dict keys match what you see.

If the first test run in step 5 fails at the login step, this is almost
always why - just paste me a screenshot of the login page's Inspect view
and I'll fix it directly.

### 5. Test it
- Go to the repo's **Actions** tab -> "Check Enago Assignments" -> **Run workflow** to trigger it manually.
- Check the run's logs to confirm login succeeded and assignments were parsed.
- First run won't send notifications (nothing to compare against yet) - it just saves a baseline. From the second run onward, anything new triggers a push.

## Adjusting frequency

Edit the `cron` line in `.github/workflows/check-assignments.yml`. It's
currently every 5 minutes (`*/5 * * * *`). GitHub's free tier allows
generous scheduled runs, but very high frequency (e.g. every minute) isn't
reliably supported - 5 minutes is a good balance of "real-time enough"
without hammering their servers.

## A note on security

Your Enago credentials are stored as encrypted GitHub secrets - reasonably
safe, but not zero-risk, since anyone with admin access to the repo could
read them. Keep the repo private and don't add collaborators you don't
trust with your Enago login.
