import logging
import asyncio
import pickle
import os
from telegram import Update
from telegram.ext import filters, MessageHandler, ApplicationBuilder, CommandHandler, ContextTypes
from secrets import OWN_CHAT_ID, TOKEN, PRIVILEGED_USERS
from targets import targets
from time import sleep

WORKDIR = "/data/"
DEVMODE = False

logging.basicConfig(
    format="%(asctime)s [%(levelname)s]: %(message)s",
    level=logging.INFO,
    filename=WORKDIR + "hestia.log"
)

def initialize():
    if not os.path.exists(WORKDIR + "subscribers"):
        logging.info("Initializing new subscribers database file...")
        with open(WORKDIR + "subscribers", 'wb') as file:
            pickle.dump(set([OWN_CHAT_ID]), file)

#    if os.path.exists(WORKDIR + "HALT"):
#        logging.warning("Scraper is halted.")
#        await context.bot.send_message(OWN_CHAT_ID, "Scraper is halted. Use /resume to resume scraping.")
#        
#    if os.path.exists(WORKDIR + "DEVMODE"):
#        DEVMODE = True
#        logging.warning("Dev mode is enabled.")
#        await context.bot.send_message(OWN_CHAT_ID, "Dev mode enabled. Use /nodev to resume publishing updates.")

async def load_subs(update, context):
    try:
        with open(WORKDIR + "subscribers", 'rb') as file:
            return pickle.load(file)
    except BaseException as e:
        await transmit_error(e, update, context)
        return None

async def transmit_error(e, update, context):
    log_msg = f'''Error loading file for subscriber: {update.effective_chat.username} ({update.effective_chat.id})
{repr(e)}'''

    logging.error(log_msg)
    await context.bot.send_message(OWN_CHAT_ID, log_msg)
    
    message = "Something went wrong there, but I've let @WTFloris know! He'll let you know once he's fixed his buggy-ass code."
    await context.bot.send_message(update.effective_chat.id, message)
    
def privileged(update, context, command, check_only=True):
    if update.effective_chat.id in PRIVILEGED_USERS:
        if not check_only:
            logging.info(f"Command {command} by ID {update.effective_chat.id}: {update.message.text}")
        return True
    else:
        if not check_only:
            logging.warning(f"Unauthorized {command} attempted by ID {update.effective_chat.id}.")
            # TODO this function must be await but the privilege check must not be async
            #await context.bot.send_message(update.effective_chat.id, "You're not allowed to do that!")
        return False
    
async def new_sub(subs, update, context):
    name = update.effective_chat.username
    if name is None:
        name = await context.bot.get_chat(sub).first_name
        
    log_msg = f"New subscriber: {name} ({update.effective_chat.id})"
    logging.info(log_msg)
    await context.bot.send_message(chat_id=OWN_CHAT_ID, text=log_msg)
    
    subs.add(update.effective_chat.id)
    with open(WORKDIR + "subscribers", 'wb') as file:
        pickle.dump(subs, file)
        
    message ="""Hi there!

I scrape real estate websites for new rental homes in and around Amsterdam. For more info on which websites I scrape with which parameters, say /websites.

Please note that some real estate websites provide paid members with early access, so some of the homes I send you will be unavailable.

You are now recieving updates when I find something new! If you want me to stop, just say /stop.

If you have any issues or questions, let @WTFloris know!"""
    await context.bot.send_message(update.effective_chat.id, message)

async def start(update, context):
    subs = await load_subs(update, context)

    if subs is None:
        return 1

    if update.effective_chat.id in subs:
        message = "You are already a subscriber, I'll let you know if I see any new rental homes online!"
        await context.bot.send_message(update.effective_chat.id, message)
    else:
        await new_sub(subs, update, context)
        

async def stop(update, context):
    subs = await load_subs(update, context)

    if subs is None:
        return 1

    if update.effective_chat.id in subs:
        subs.remove(update.effective_chat.id)
        with open(WORKDIR + "subscribers", 'wb') as file:
            pickle.dump(subs, file)
        log_msg = f"Removed subscriber: {update.effective_chat.username} ({update.effective_chat.id})"
        logging.info(log_msg)
        await context.bot.send_message(chat_id=OWN_CHAT_ID, text=log_msg)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="You will no longer recieve updates for new listings."
    )

async def reply(update, context):
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Sorry, I can't talk to you, I'm a just a scraper. If you want to see what commands I support, say /help. If you are lonely and want to chat, try ChatGPT."
    )

async def announce(update, context):
    if not privileged(update, context, "announce", check_only=False): return

    with open(WORKDIR + "subscribers", 'rb') as subscribers_file:
        subs = pickle.load(subscribers_file)

    for sub in subs:
        try:
            # If a user blocks the bot, this would throw an error and kill the entire broadcast
            await context.bot.send_message(sub, update.message.text[10:])
        except BaseException as e:
            logging.warning(f"Exception while broadcasting announcement to {sub}: {repr(e)}")
            continue
            
async def websites(update, context):
    message = "Here are the websites I scrape, and with which search parameters (these differ per website):\n\n"
    
    for target in targets:
        message += f"Agency: {target['info']['agency']}\n"
        message += f"Website: {target['info']['website']}\n"
        message += f"Search parameters: {target['info']['parameters']}\n"
        message += f"\n"
        
    await context.bot.send_message(update.effective_chat.id, message[:-1])
    sleep(2)
    
    message = "If you want more information, you can also read my source code: https://github.com/wtfloris/hestia"
    await context.bot.send_message(update.effective_chat.id, message)
    
async def get_sub_info(update, context):
    if not privileged(update, context, "get_sub_info", check_only=False): return
        
    sub = update.message.text.split(' ')[1]
    chat = await context.bot.get_chat(sub)
    
    message = f"Username: {chat.username}\n"
    message += f"Name: {chat.first_name} {chat.last_name}\n"
    message += f"Bio: {chat.bio}"
    
    await context.bot.send_message(update.effective_chat.id, message)
    
# This writes a HALT file to stop the scraper, in case some API has changed
# and all results for a website are ending up in the bot
async def halt(update, context):
    if not privileged(update, context, "halt", check_only=False): return
    
    open(WORKDIR + "HALT", "w").close()
    
    message = "Halting scraper."
    await context.bot.send_message(update.effective_chat.id, message)
    
# Resumes the scraper by removing the HALT file. Note that this may create
# a massive update broadcast. Consider putting Hestia on dev mode first.
async def resume(update, context):
    if not privileged(update, context, "resume", check_only=False): return
        
    try:
        os.remove(WORKDIR + "HALT")
    except FileNotFoundError:
        pass
        
    message = "Resuming scraper. Note that this may create a massive update within the next 5 minutes. Consider enabling /dev mode."
    await context.bot.send_message(update.effective_chat.id, message)

async def enable_dev(update, context):
    if not privileged(update, context, "resume", check_only=False): return
    
    DEVMODE = True
    open(WORKDIR + "DEVMODE", "w").close()
    
    message = "Dev mode enabled."
    await context.bot.send_message(update.effective_chat.id, message)
    
async def disable_dev(update, context):
    if not privileged(update, context, "resume", check_only=False): return
    
    DEVMODE = False
    try:
        os.remove(WORKDIR + "DEVMODE")
    except FileNotFoundError:
        pass
    
    message = "Dev mode disabled."
    await context.bot.send_message(update.effective_chat.id, message)

async def help(update, context):
    message = f"I can do the following for you:\n"
    message += "\n"
    message += "/help - Show this message\n"
    message += "/start - Subscribe to updates\n"
    message += "/stop - Stop recieving updates\n"
    message += "/websites - Show info about the websites I scrape"
    
    if privileged(update, context, "help", check_only=True):
        message += "\n\n"
        message += "Admin commands:\n"
        message += "/announce - Broadcast a message to all subscribers\n"
        message += "/getsubinfo <sub_id> - Get info by subscriber ID\n"
        message += "/halt - Halts the scraper\n"
        message += "/resume - Resumes the scraper"

    await context.bot.send_message(update.effective_chat.id, message)

if __name__ == '__main__':
    initialize()

    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("stop", stop))
    application.add_handler(CommandHandler("announce", announce))
    application.add_handler(CommandHandler("websites", websites))
    application.add_handler(CommandHandler("getsubinfo", get_sub_info))
    application.add_handler(CommandHandler("halt", halt))
    application.add_handler(CommandHandler("resume", resume))
    application.add_handler(CommandHandler("dev", enable_dev))
    application.add_handler(CommandHandler("nodev", disable_dev))
    application.add_handler(CommandHandler("help", help))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), reply))
    
    application.run_polling()
