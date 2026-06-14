

<p align="center">
  <img
    width="512"
    height="128"
    alt="MiniOS logo"
    src="https://github.com/codefl0w/MiniOS/blob/main/github_res/MiniOS_Logo.png"
  />
</p>

<p align="center">
  MiniOS is a small Flask app drawer for low-end feature-phone browsers.<br>
  It aims to connect feature phones to usual everyday websites without compromising the "dumbphone" aspect.
  
</p>
<p align="center">
  <img
    alt="MiniOS Version"
    src="https://codefl0w.xyz/gh-boards/out/codefl0w/profile/badge_custom_2.svg"
  />


## Table of Contents

* [Run](#run)
* [Hosting](#hosting)

  * [PythonAnywhere](#pythonanywhere)
  * [Render](#render)
  * [Railway](#railway)
  * [Other hosts](#other-hosts)
* [.env](#env)

  * [Minigram](#minigram)
  * [AI](#ai)
  * [Gmail](#gmail)
* [Settings](#settings)
* [Apps](#apps)
* [Extras](#extras)

## Run

To host your own MiniOS configuration and access it anywhere, the best way is to run the Flask server on a Python hosting service.

PythonAnywhere is the easiest option for a simple free setup as MiniOS doesn't even come close to filling up the free quota. It also doesn't have coldstart or any other downsides aside from asking you to renew your site once a month.

 Render or Railway can also work well, especially if you prefer GitHub-based deployment.

For local testing, clone or download the repository and install the required packages:

```bash
pip install -r requirements.txt
```

Then run:

```bash
python main.py
```

Open MiniOS at:

```text
http://127.0.0.1:2000/
```

If you use a virtual environment:

```bash
python -m venv .venv
```

On Linux/macOS:

```bash
source .venv/bin/activate
```

On Windows:

```bat
.venv\Scripts\activate
```

Then install dependencies and run MiniOS:

```bash
pip install -r requirements.txt
python main.py
```

## Hosting

MiniOS is a Flask app, so it needs a host that can run Python web apps.

Good options:

| Host           | Status      | Notes                                                                |
| -------------- | ----------- | -------------------------------------------------------------------- |
| PythonAnywhere | Recommended | Simple Flask hosting, best free tier for MiniOS instances. Doesn't have native .env support.            |
| Render         | Partial        | Easy GitHub deployment. Free services will sleep after inactivity.                     |
| Railway        | Good        | Easy GitHub deployment and environment variables. Limits are not ideal. |
| Fly.io         | Good        | More technical, but suitable for small Flask apps.                   |
| Koyeb          | Good        | Can run Python web services.                                         |
| Replit         | Partial     | Fine for testing, less ideal for permanent hosting.                  |
| Vercel         | Limited     | Possible only with serverless adaptation. Not the default path.      |
| Netlify        | Limited     | Better for static sites. Not recommended for normal Flask hosting.   |
| VPS            | Good        | Best control, but requires manual server setup.                      |

### PythonAnywhere

PythonAnywhere is the most straightforward host for MiniOS.

Basic setup:

1. Create a PythonAnywhere account.
2. Create a web app and select Flask when asked. Make sure you rename the quickstart script from `flask_app.py` to `main.py` .
3. Navigate to your files, where you see `main.py`. Upload all MiniOS scripts. Create an `icons` directory and upload all icons as well. Make sure you don't change the project structure.
4. Navigate to the **Web** section and reload your site.


You can then use your personal MiniOS on your phone. Keep in mind that environment variables only reload once per site reload, so you must reload your website on PythonAnywhere again if you change your variables.



### Render

Render can deploy MiniOS directly from a GitHub repository.

Typical setup:

```text
Runtime: Python
Build command: pip install -r requirements.txt
Start command: python main.py
```


Render supports environment variables to be injected directly on the web, so you don't need to fill your .env file. You can create the variables and fill them in:

```text
BOT_TOKEN
ME_ID
GEMINI_API_KEY
MAIL_USERNAME
MAIL_PASSWORD
MAIL_FROM
```


### Railway

Railway can run MiniOS as a Python web app.

Typical setup:

```text
Build command: pip install -r requirements.txt
Start command: python main.py
`````

Use Railway variables for secrets instead of committing `.env`, same as Render above.


### Other hosts

Other possible options:

* Fly.io
* Koyeb
* Replit
* Glitch
* A small VPS
* A home server
* A home server behind Cloudflare Tunnel
* A Raspberry Pi or similar device

For the simplest setup, use PythonAnywhere.

For GitHub-based deployment, use Render or Railway.

For full control, use a VPS.

## .env

 For your API keys and Gmail password, copy `.env.example` to `.env` and fill values.

MiniOS loads `.env` from the same folder as `main.py`, then injects values into `os.environ` before app modules read config. This works on hosts where normal environment variables are not available. On Render or Railway, you can use their own environment secrets section instead.

`.env` format:

```text
KEY=value
MAIL_PASSWORD=xxxx xxxx xxxx xxxx
```

Do not share `.env` publicly.

Do not commit `.env` to a public repository.

**Minigram:**

Minigram is a bot bridge that connects you to Telegram. Use Telegram's official BotFather app to create a bot, then copy its token and paste it into your `.env` file.

```text
BOT_TOKEN=                         # Your bot's token. Do NOT share this publicly!
ME_ID=                             # Your user ID. Find it by running the @userinfobot on Telegram
MINIGRAM_ENABLE_ADMIN_ROUTES=1     # Must be enabled for proper webhook setup. Can be set to 0 after successful setup.
```

To set up the bot bridge, navigate to:

```text
{URL}/set_webhook
```

You can check the connection any time at:

```text
{URL}/webhook_info
```

Using a bot has caveats. For example, the receiver must start a chat with your bot first, so your bot doesn't get treated as a blocked user. This is a one-time setup for each receiver.

Bots need user IDs to work. You can view IDs either via the `@userinfobot` or from a Telegram chat link:

```text
https://web.telegram.org/a/#1234567
```

The number at the end is the user ID. It doesn't have to be 7 digits.

After the webhook is configured, you can disable admin routes:

```text
MINIGRAM_ENABLE_ADMIN_ROUTES=0
```

**AI:**

```text
GEMINI_API_KEY=                   # You can generate a free key at Google AI Studio.
GEMINI_MODEL=gemini-3.5-flash     # Default free model. Change if you have Pro.
```

**Gmail:**

```text
MAIL_USERNAME=      # Your mail address
MAIL_PASSWORD=      # 16-digit Gmail App Login code. Generate one: https://support.google.com/mail/answer/185833
MAIL_FROM=          # Optional for sending. Use your mail address if you'll fill it.
```

Use a Gmail App Password, not your normal Gmail password.

## Settings

Use `/settings` for non-secret app settings:

* Weather location and coordinates
* Minigram contacts and timestamp settings
* Finance currency
* Boards subreddit list
* News defaults
* Gmail limit and cache TTL

Settings are stored in `settings.json`.

Do not store passwords, tokens, API keys, mail credentials, or bot secrets in `settings.json`.

## Apps

MiniOS currently has 8 apps, with the following functionalities:

### Minigram

Minimal Telegram web client. Only for texting trusted contacts, not suitable for groupchats.

Minigram supports these features:

|Action|  Support| Description |
|--|--| -- |
| Send messages | ✅ |
| Receive messages | ✅ | 
| Send Emojis|✅  | Minigram has an ASCII-to-Emoji conversion feature. When you send "<3", the receiver sees a "💛" instead.
| Receive Emojis| ✅ | The same feature works the other way too. See all supported emojis below. 
| Send pictures| ❌| MocorOS likely doesn't support uploads. To be tested and maybe changed later on.
| Receive pictures| ✅ | Minigram can download the pictures, downscale them and display them in the chat UI directly.
| Send stickers| ❌ | 
| Receive stickers| ❌ | Could change in future updates.


#### Emoji conversion

Minigram converts simple ASCII expressions into emojis when sending messages. When receiving messages, supported emojis are converted back into ASCII so they can be displayed reliably on limited browsers.

**Sending**

| Typed in Minigram | Sent as |
| ----------------- | ------- |
| `<3`              | 💛      |
| `:)`              | 🙂      |
| `:D`              | 😀      |
| `:'D`             | 😂      |
| `;)`              | 😉      |
| `:3`              | 😘      |
| `:(`              | ☹️      |
| `:p`              | 😛      |

**Receiving**

| Received emoji | Shown in Minigram |
| -------------- | ----------------- |
| 💛             | `<3`              |
| ❤️             | `<3`              |
| 💙             | `<3`              |
| 💚             | `<3`              |
| 💜             | `<3`              |
| 🙂             | `:)`              |
| 😀             | `:D`              |
| 😂             | `:'D`             |
| 😉             | `;)`              |
| 😘             | `:3`              |
| ☹️             | `:(`              |
| 😛             | `:p`              |

Most heart emojis are collapsed into `<3` when received. Sending `<3` currently sends the yellow heart (💛).




### Weather

Simple weather app based on Open-Meteo metrics. Shows the current and oncoming weather, as well as extra information such as pressure, humidity etc.

Temperature can be displayed in either celcius or fahrenheit. You can change this from the settings app any time, along with your desired location.

### Notes

Simple notes app. Supports saving unlimited notes.

### AI

Simple AI chat based on Google Gemini. Supports sending and receiving plain text.

Gemini's responses will be short and plain, as declared on the system prompt in `ai.py`.

### Finance

Simple app to track your spendings. Supports changing the currency from the settings.

### Boards

RSS-based Reddit reader. Supports displaying posts with text and pictures. Listed communities can be changed from the settings app.

### News

RSS-based Google News app. Shows short descriptions of news, but full reader isn't ready yet.

Default topic or language can be changed from the settings app.

### Gmail

Simple Gmail app. Supports viewing and sending mails. Since Google responds slowly, mails will be cached instead of being reloaded each time.

Cache expiry time and maximum shown mail count can be changed from the settings app.

## Extras

Enjoy my work? Please consider a small donation!

<a href="https://buymeacoffee.com/fl0w" target="_blank" rel="noopener noreferrer">
  <img width="350" alt="yellow-button" src="https://github.com/user-attachments/assets/2e6d44c8-9640-4cb3-bcc8-989595d6b7e9"/>
</a>
