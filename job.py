from __future__ import print_function
import pickle
import os.path
import json
import time
import logging
from html import escape
from collections import namedtuple
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
import telegram


def main():
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s',
                     level=logging.INFO)
    logging.info('tg--gmail-bridge - dupokopacz')

    # Load config from file
    config = None
    if os.path.exists('config.json'):
        with open('config.json', 'r') as json_file:
            config = json.load(json_file)

    if config:
        logging.info('Config loaded')
    else:
        logging.critical('Missing config.json file!')
        return

    # Load tg bot secret
    tg_secret = None
    if os.path.exists('bot.token'):
        with open('bot.token', 'r') as tg_token:
            tg_secret = tg_token.read()

    if config:
        logging.info('Telegram secret loaded')
    else:
        logging.critical('Missing bot.token file!')
        return

    # Try to authenticate with the Google API
    creds = None
    # The file token.pickle stores the user's access and refresh tokens
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    # Check if there are any supplied creds and regenerate them if needed
    logging.info('Checking token...')
    if not creds:
        logging.critical('Missing token.pickle file, please generate with create_token.py!')
    
    # Token might be expired, refresh it if needed
    if not creds.valid:
        if creds.expired and creds.refresh_token:
            logging.warn('Token has expired')
            logging.info('Refreshing token')
            creds.refresh(Request())

        if creds.valid:
            logging.info('Token refreshed!')
            # Save refreshed token
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
        else:
            logging.critical('Cannot refresh expired token')
            return
    else:
        logging.info('Token is valid')

    # Initialize APIs
    logging.info('Initializing APIs')
    gmail = build('gmail', 'v1', credentials=creds, cache_discovery=False)
    bot = telegram.Bot(token=tg_secret)

    # Check if tg bot is initialized
    if not bot.get_me():
        logging.critical('Invalid bot secret!')
        gmail.close()
        return
    
    logging.info(f'Bot name: {bot.get_me()["first_name"]}')
    logging.info('Auth completed!')

    # Check under whose account the bot is running
    profile = gmail.users().getProfile(userId='me').execute()
    logging.info(f'Running as {profile["emailAddress"]}')

    # If label does not exist, create a new one and mark all emails in 
    # label = None
    # labels = gmail.users().labels().list(userId='me').execute().get('labels', [])
    # for l in labels:
    #     if l['name'] == config['label']:
    #         label = l
    #         logging.info(f'Using label: {label["name"]}')
    
    # if not label:
    #     logging.error('Label not found, exiting!')
    #     gmail.close()
    #     return

    # Check when the script was previously executed
    lastRun = None
    if os.path.exists('lastRun'):
        with open('lastRun', 'r') as f:
            lastRun = f.read()

    if lastRun:
        logging.info('Normal run, looking for new unprocessed emails')
        logging.warn('Some results might have been ignored, pls add nextPageToken support')

        # Get email threads
        threads = gmail.users().threads().list(userId='me', q=config['threadQuery'] + f' after: {lastRun}', maxResults=config['maxResults']).execute()

        # If no new, exit
        if not threads.get('threads'):
            logging.info('No new email threads')
            gmail.close()
            return

        logging.info(f'Got {len(threads["threads"])} message threads')
        
        # Get messages from threads
        Message = namedtuple('Message', ['subject', 'sender'])
        messages = []

        logging.info(f'Getting messages...')
        for t in threads['threads']:
            thread = gmail.users().threads().get(userId='me', id=t['id']).execute()
            
            # Mails can be additionaly filtered here
            if True:
                sen = ""
                sub = ""
                for header in thread['messages'][0]['payload']['headers']:
                    if header['name'] == "From":
                        sen = header['value']
                    if header['name'] == "Subject":
                        sub = header['value']

                messages.append(Message(subject=sub, sender=sen))

        logging.info(f'{len(messages)} messages retreived!')

        # Format tg message
        if len(messages) > 0:
            tg_message = "You've got mail:\n\n"

            for msg in messages:
                logging.debug(f'{msg.subject} | {msg.sender}')
                tg_message += f'<b>{escape(msg.subject)}</b>\n<code>from {escape(msg.sender)}</code>\n\n'

            # Send tg message
            logging.info('Sending tg message...')
            bot.send_message(
                config['chatId'],
                tg_message,
                parse_mode='HTML',
                disable_notification=True,
                disable_web_page_preview=True
            )
            logging.info('Message sent!')

        else:
            logging.info('No new messages - not sending anything')
        
    else:
        logging.info('First run, doing nothing')
        bot.send_message(config['chatId'], f"New config, who's there? \n\n Running as: {profile['emailAddress']} \n (Probably everything works :D)", disable_notification=True)

    # Save epoch when the script was executed
    with open('lastRun', 'w') as f:
        lastRun = f.write(str(int(time.time())))
        logging.info('Timestamp saved')

    logging.info('Exiting')
    gmail.close()

if __name__ == '__main__':
    main()
