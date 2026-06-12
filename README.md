
# MiniOS


MiniOS is a small Flask app drawer for low-end feature-phone browsers. It aims to connect feature phones to usual everyday websites without compromising the "dumbphone" aspect.


## Run

  To host your own MiniOS configuration and access it anywhere, the best way is to run the Flask server on a Python service. Render or Railway would suffice but the best service is PythonAnywhere since it's completely free.

To set up MiniOS, clone or download the repository contents into PythonAnywhere and make sure PythonAnywhere is configured to run `main.py`.


For local tests, run the script on your machine and view it at:

```text

http://127.0.0.1:2000/

```

  

## .env

  

Do not put secrets in `settings.json`. Copy `.env.example` to `.env` and fill values.

  

MiniOS loads `.env` from the same folder as `main.py`, then injects values into `os.environ` before app modules read config. This works on hosts where normal environment variables are not available. On Render or Railway, you can use their own environment secrets section instead.

  

`.env` format:

  

```text

KEY=value

MAIL_PASSWORD=xxxx xxxx xxxx xxxx

```

  

**Minigram:**

Minigram is a bot bridge that connects you to Telegram. Use Telegram's official BotFather app to create a bot, then copy its token and paste it into your .env file.
 
```text

BOT_TOKEN=

ME_ID= #Your user ID. Find it by running the @userinfobot on Telegram

MINIGRAM_ENABLE_ADMIN_ROUTES=1 # Must be enabled for proper webhook setup.
                               # can be set to 0 after successful setup.

```
To set up properly, navigate to {URL}/set_webhook to connect to your bot. You can check the connection any time at /webhook_info.
  
Using a bot has caveats. For example, the receiver must start a chat with your bot first, so your bot doesn't get treated as a blocked user. This is a one-time setup for each receiver.

Bots need user IDs to work. You can view IDs either via the @userinfobot or from a Telegram chat link:

    https://web.telegram.org/a/#1234567

The number at the end is the user ID. It doesn't have to be 7 digits.

**AI:**

  

```text

GEMINI_API_KEY= # You can generate a free key at Google AI Studio.

GEMINI_MODEL=gemini-3.5-flash # Default free model. Change if you have Pro.

```

  

**Gmail:**

  

```text

MAIL_USERNAME= # Your mail address

MAIL_PASSWORD= # 16-digit Gmail App Login code. Generate one: https://support.google.com/mail/answer/185833

MAIL_FROM= # Optional for sending. Use your mail address if you'll fill it.

```

  

## Settings

  

Use `/settings` for non-secret app settings:

  

-  Weather location and coordinates

-  Minigram contacts and timestamp settings

-  Finance currency

-  Boards subreddit list

-  News defaults

-  Gmail limit and cache TTL

  

Settings are stored in `settings.json`. 

### Extras

Enjoy my work? Please consider a small donation!

<a href="https://buymeacoffee.com/fl0w" target="_blank" rel="noopener noreferrer">
  <img width="350" alt="yellow-button" src="https://github.com/user-attachments/assets/2e6d44c8-9640-4cb3-bcc8-989595d6b7e9"/>
</a>

