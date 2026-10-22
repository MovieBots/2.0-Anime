import os, re, json, sqlite3, logging, urllib.request, urllib.error, html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

TOKEN=os.getenv('BOT_TOKEN','').strip(); ADMIN_IDS={int(x) for x in os.getenv('ADMIN_IDS','').split(',') if x.strip().isdigit()}
DB_PATH=os.getenv('DB_PATH','animebot.db'); SOURCE_CHANNEL_ID=os.getenv('SOURCE_CHANNEL_ID','').strip()
FSUB_CHANNELS=[x.strip() for x in os.getenv('FSUB_CHANNELS','').split(',') if x.strip()]
FSUB_LINKS=[x.strip() for x in os.getenv('FSUB_LINKS','').split(',') if x.strip()]
GEMINI_API_KEY=os.getenv('GEMINI_API_KEY','').strip(); ANILIST_URL='https://graphql.anilist.co'
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s'); log=logging.getLogger('animebot')

def db():
 c=sqlite3.connect(DB_PATH); c.row_factory=sqlite3.Row
 c.execute('''CREATE TABLE IF NOT EXISTS episodes(id INTEGER PRIMARY KEY, title TEXT NOT NULL, episode TEXT NOT NULL, language TEXT DEFAULT 'Unknown', quality TEXT DEFAULT 'Unknown', file_id TEXT NOT NULL, file_type TEXT NOT NULL, source_message INTEGER, UNIQUE(title,episode,language,quality))''')
 c.execute('CREATE TABLE IF NOT EXISTS users(user_id INTEGER PRIMARY KEY)'); c.commit(); return c

def anilist(q):
 gql='query ($search:String){Page(page:1,perPage:5){media(search:$search,type:ANIME,sort:SEARCH_MATCH){title{english romaji native} coverImage{large} description(asHtml:false) episodes seasonYear averageScore siteUrl}}}'
 body=json.dumps({'query':gql,'variables':{'search':q}}).encode(); req=urllib.request.Request(ANILIST_URL,data=body,headers={'Content-Type':'application/json','Accept':'application/json','User-Agent':'PowerfulAnimeBot/1.0'})
 with urllib.request.urlopen(req,timeout=15) as r: return json.loads(r.read().decode()).get('data',{}).get('Page',{}).get('media',[])
def title_of(m):
 t=m.get('title') or {}; return t.get('english') or t.get('romaji') or t.get('native') or 'Unknown anime'
def parse_caption(caption, filename=''):
 text=(caption or '')+'\n'+(filename or '')
 # strip promotional/footer lines
 lines=[x.strip() for x in text.splitlines() if x.strip() and not re.search(r'@\w+|https?://|main\s*:|anime movie\s*:',x,re.I) and not re.fullmatch(r'[-_━─\s📗]+',x)]
 ep=re.search(r'(?:episode|ep)\s*[-:#.]?\s*(\d+(?:\.\d+)?)',text,re.I)
 quality=re.search(r'\b(2160p|1440p|1080p|720p|480p|360p|4k)\b',text,re.I)
 language=re.search(r'\b(Hindi|Japanese|English|Tamil|Telugu|Dual Audio|Multi Audio|Urdu)\b',text,re.I)
 # Candidate title is any line not solely metadata
 candidates=[]
 for line in lines:
  if re.search(r'episode\s*[-:#.]?\s*\d+|quality\s*:|language\s*:',line,re.I): continue
  if re.search(r'\b(2160p|1440p|1080p|720p|480p|360p|4k)\b',line,re.I): continue
  clean=re.sub(r'^[🎬📺✨🔰📥\W_]+','',line).strip()
  if len(clean)>=3 and len(clean)<100: candidates.append(clean)
 title=candidates[0] if candidates else ''
 return title, ep.group(1) if ep else '', language.group(1) if language else 'Unknown', quality.group(1).upper() if quality else 'Unknown'

async def ai_title_from_thumbnail(msg, context):
 if not GEMINI_API_KEY or not msg.video or not msg.video.thumbnail: return ''
 try:
  f=await context.bot.get_file(msg.video.thumbnail.file_id); data=await f.download_as_bytearray()
  payload={'contents':[{'parts':[{'text':'Identify the anime title visible in this frame. Return ONLY the official anime title, no episode number or explanation. If uncertain return UNKNOWN.'},{'inline_data':{'mime_type':'image/jpeg','data':__import__('base64').b64encode(data).decode()}}]}]}
  req=urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key='+GEMINI_API_KEY,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
  with urllib.request.urlopen(req,timeout=25) as r: out=json.loads(r.read().decode())
  result=out['candidates'][0]['content']['parts'][0]['text'].strip().strip('"')
  return '' if result.upper()=='UNKNOWN' else result[:100]
 except Exception: log.exception('AI thumbnail recognition failed'); return ''

async def is_subscribed(user_id, context):
 if not FSUB_CHANNELS: return True
 for channel in FSUB_CHANNELS:
  try:
   member=await context.bot.get_chat_member(channel,user_id)
   if member.status not in ('member','administrator','creator') and not getattr(member,'is_member',False): return False
  except Exception: return False
 return True
async def fsub_prompt(msg):
 rows=[]
 for i,link in enumerate(FSUB_LINKS): rows.append([InlineKeyboardButton(f'📢 Join Channel {i+1}',url=link)])
 rows.append([InlineKeyboardButton('✅ I Joined — Check Again',callback_data='check_fsub')])
 await msg.reply_text('🔒 Bot use karne ke liye pehle required channel(s) join karein, phir Check Again dabayein.',reply_markup=InlineKeyboardMarkup(rows))
async def allowed(update,context):
 if await is_subscribed(update.effective_user.id,context): return True
 await fsub_prompt(update.effective_message); return False

def menu(is_admin=False):
 rows=[[InlineKeyboardButton('🔎 Search Anime',callback_data='search_help'),InlineKeyboardButton('📚 Episode Catalog',callback_data='episodes')],
       [InlineKeyboardButton('🌟 Popular Anime',callback_data='popular'),InlineKeyboardButton('ℹ️ Help',callback_data='help')]]
 if is_admin: rows.append([InlineKeyboardButton('🛡️ Admin Control Panel',callback_data='admin:home')])
 return InlineKeyboardMarkup(rows)

def admin_keyboard():
 return InlineKeyboardMarkup([
  [InlineKeyboardButton('📊 Statistics',callback_data='admin:stats'),InlineKeyboardButton('⚙️ Settings',callback_data='admin:settings')],
  [InlineKeyboardButton('📥 Upload Guide',callback_data='admin:upload'),InlineKeyboardButton('🔐 Force Subscribe',callback_data='admin:fsub')],
  [InlineKeyboardButton('📡 Source Channel',callback_data='admin:source')],
  [InlineKeyboardButton('⬅️ User Menu',callback_data='admin:user_menu')]
 ])

def is_admin_user(user_id): return bool(user_id and user_id in ADMIN_IDS)

async def admin_only(update, context):
 user=update.effective_user
 if is_admin_user(user.id if user else None): return True
 msg=update.effective_message
 if msg: await msg.reply_text('⛔ Ye command sirf authorized Admin ke liye hai.')
 return False

async def admin_panel(update, context):
 if not await admin_only(update, context): return
 await update.effective_message.reply_text('🛡️ <b>ADMIN CONTROL CENTER</b>\n\nYahan se bot status aur configuration dekhein. Sensitive tokens kabhi chat mein show nahi kiye jaate.',parse_mode='HTML',reply_markup=admin_keyboard())
async def start(u:Update,c:ContextTypes.DEFAULT_TYPE):
 if not await allowed(u,c): return
 con=db(); con.execute('INSERT OR IGNORE INTO users VALUES(?)',(u.effective_user.id,)); con.commit(); con.close()
 await u.effective_message.reply_text('🎌 Welcome to Anime Finder!\nAnime ka naam type karein, ya /search Naruto use karein. Episodes source channel se catalog hote hain.',reply_markup=menu(is_admin_user(u.effective_user.id)))
async def help_cmd(u,c):
 await u.effective_message.reply_text('🎌 <b>ANIME HUB HELP</b>\n\n🔎 Search: /search Naruto ya anime ka naam type karein\n📚 Episodes: /episodes\n👥 Group mein bhi search kar sakte hain.\n\nAdmin management commands sirf authorized Admin IDs ke liye hain.',parse_mode='HTML',reply_markup=menu(is_admin_user(u.effective_user.id)))
async def search_cmd(u,c):
 if not await allowed(u,c): return
 q=' '.join(c.args).strip()
 if not q: await u.effective_message.reply_text('Example: /search Naruto'); return
 try: results=anilist(q)
 except Exception: log.exception('AniList error'); await u.effective_message.reply_text('Anime database abhi unavailable hai, baad mein try karein.'); return
 if not results: await u.effective_message.reply_text('Anime nahi mila. Spelling check karein.'); return
 for m in results:
  title=title_of(m); desc=re.sub(r'<[^>]+>','',m.get('description') or 'Description unavailable.'); desc=desc[:450]+'…' if len(desc)>450 else desc
  requester=u.effective_user
  mention=(f'\n👤 Requested by <a href="tg://user?id={requester.id}">{html.escape(requester.full_name)}</a>' if u.effective_chat and u.effective_chat.type in ('group','supergroup') and requester else '')
  caption=f"🎬 <b>{html.escape(title)}</b>{mention}\n📺 Episodes: {m.get('episodes') or 'Unknown'}\n📅 Year: {m.get('seasonYear') or 'Unknown'}\n⭐ Score: {m.get('averageScore') or 'N/A'}/100\n\n{html.escape(desc)}"
  kb=InlineKeyboardMarkup([[InlineKeyboardButton('📥 Available Episodes',callback_data='title:'+title[:55])],[InlineKeyboardButton('AniList details',url=m.get('siteUrl') or 'https://anilist.co')]])
  cover=(m.get('coverImage') or {}).get('large')
  try:
   if cover: await u.effective_message.reply_photo(cover,caption=caption,parse_mode='HTML',reply_markup=kb)
   else: await u.effective_message.reply_text(caption,parse_mode='HTML',reply_markup=kb)
  except Exception: await u.effective_message.reply_text(caption,parse_mode='HTML',reply_markup=kb)
async def send_episode_rows(msg, title=None):
 con=db();
 if title: rows=con.execute('SELECT * FROM episodes WHERE lower(title) LIKE lower(?) ORDER BY episode,quality',(f'%{title}%',)).fetchall()
 else: rows=con.execute('SELECT * FROM episodes ORDER BY title,episode LIMIT 30').fetchall()
 con.close()
 if not rows: await msg.reply_text('Is anime ke episodes catalog mein abhi nahi hain.'); return
 for r in rows:
  label=f"🎬 <b>{html.escape(r['title'])}</b>\n📺 Episode {html.escape(r['episode'])}\n🌐 {html.escape(r['language'])} • 🎞 {html.escape(r['quality'])}"
  await msg.reply_text(label,parse_mode='HTML',reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton('▶️ Send video',callback_data=f"play:{r['id']}")]]))
async def episodes_cmd(u,c):
 if not await allowed(u,c): return
 await send_episode_rows(u.effective_message)
async def handle_video(u,c):
 msg=u.effective_message; uid=u.effective_user.id if u.effective_user else 0
 is_source=bool(SOURCE_CHANNEL_ID and str(msg.chat_id)==SOURCE_CHANNEL_ID and u.channel_post)
 if not is_source and uid not in ADMIN_IDS: return
 cap=msg.caption or ''; fname=''
 media=msg.video or msg.document or msg.audio
 if msg.document: fname=msg.document.file_name or ''
 title,ep,lang,quality=parse_caption(cap,fname)
 if not ep:
  await msg.reply_text('Episode number caption mein nahi mila. Example: Anime Name | Episode 01 | Hindi | 1080p'); return
 if not title or re.fullmatch(r'(episode|ep)\s*\d+',title,re.I): title=await ai_title_from_thumbnail(msg,c)
 if not title:
  if uid in ADMIN_IDS: await msg.reply_text('⚠️ Anime name confidently identify nahi hua. Caption mein anime ka naam add karke dobara upload karein.');
  return
 if msg.video: fid=msg.video.file_id; typ='video'
 elif msg.document: fid=msg.document.file_id; typ='document'
 elif msg.audio: fid=msg.audio.file_id; typ='audio'
 else: return
 con=db(); con.execute('INSERT OR IGNORE INTO episodes(title,episode,language,quality,file_id,file_type,source_message) VALUES(?,?,?,?,?,?,?)',(title,ep,lang,quality,fid,typ,msg.message_id)); con.commit(); added=con.total_changes; con.close()
 if uid in ADMIN_IDS: await msg.reply_text(('✅ Added to catalog: ' if added else 'ℹ️ Duplicate skipped: ')+f'{title} | EP {ep} | {lang} | {quality}')
async def text_handler(u,c):
 if not await allowed(u,c): return
 q=(u.effective_message.text or '').strip()
 if q and not q.startswith('/'): c.args=q.split(); await search_cmd(u,c)
async def callbacks(u,c):
 q=u.callback_query; await q.answer()
 if q.data.startswith('admin:'):
  if not is_admin_user(u.effective_user.id if u.effective_user else None):
   await q.message.reply_text('⛔ Admin-only button. Aapko permission nahi hai.'); return
  action=q.data.split(':',1)[1]
  if action=='home': await q.message.reply_text('🛡️ <b>ADMIN CONTROL CENTER</b>',parse_mode='HTML',reply_markup=admin_keyboard())
  elif action=='stats':
   con=db(); n=con.execute('SELECT COUNT(*) FROM episodes').fetchone()[0]; users=con.execute('SELECT COUNT(*) FROM users').fetchone()[0]; con.close()
   await q.message.reply_text(f'📊 <b>BOT STATISTICS</b>\n👥 Registered users: {users}\n🎞 Catalog entries: {n}',parse_mode='HTML',reply_markup=admin_keyboard())
  elif action=='settings':
   await q.message.reply_text('⚙️ <b>CONFIGURATION STATUS</b>\n• Admin IDs: configured allowlist\n• Source channel: '+('configured' if SOURCE_CHANNEL_ID else 'not configured')+'\n• Force Subscribe: '+('enabled' if FSUB_CHANNELS else 'disabled')+'\n• AI title recognition: '+('API key configured' if GEMINI_API_KEY else 'disabled')+'\n• Database: SQLite\n\nTokens/API keys are hidden. Change configuration in Koyeb Environment Variables and redeploy.',parse_mode='HTML',reply_markup=admin_keyboard())
  elif action=='upload': await q.message.reply_text('📥 <b>ADMIN UPLOAD</b>\nBot ke private chat mein video/document bhejein aur caption mein anime name, episode, language aur quality likhein.\nExample:\nNaruto: Shippuden\nEpisode - 364\nLanguage - Hindi\nQuality - 1080p',parse_mode='HTML',reply_markup=admin_keyboard())
  elif action=='fsub': await q.message.reply_text('🔐 Force Subscribe channels: '+(', '.join(html.escape(x) for x in FSUB_CHANNELS) if FSUB_CHANNELS else 'Not configured')+'\nKoyeb Environment Variables mein FSUB_CHANNELS aur FSUB_LINKS set karein.',parse_mode='HTML',reply_markup=admin_keyboard())
  elif action=='source': await q.message.reply_text('📡 Source channel: '+(html.escape(SOURCE_CHANNEL_ID) if SOURCE_CHANNEL_ID else 'Not configured')+'\nBot ko source channel ka Admin banayein. Sirf naye media posts index honge.',parse_mode='HTML',reply_markup=admin_keyboard())
  elif action=='user_menu': await q.message.reply_text('🎌 User Menu',reply_markup=menu(True))
  return
 if q.data=='check_fsub':
  if await is_subscribed(u.effective_user.id,c): await q.message.reply_text('✅ Subscription verified. /start dabayein.')
  else: await q.message.reply_text('Abhi required channel membership confirm nahi hui. Join karke phir try karein.')
 elif q.data=='search_help': await q.message.reply_text('Anime ka naam type karein, jaise Naruto, ya /search Naruto')
 elif q.data=='episodes': await send_episode_rows(q.message)
 elif q.data=='help': await help_cmd(u,c)
 elif q.data=='popular':
  try: results=anilist('popular anime')
  except Exception: results=[]
  if not results: await q.message.reply_text('Popular list abhi load nahi hui. /search Naruto try karein.')
  else:
   await q.message.reply_text('🌟 Popular search ideas: Naruto, One Piece, Demon Slayer, Jujutsu Kaisen, Solo Leveling')
 elif q.data.startswith('title:'): await send_episode_rows(q.message,q.data[6:])
 elif q.data.startswith('play:'):
  if not await is_subscribed(u.effective_user.id,c): await fsub_prompt(q.message); return
  try:
   eid=int(q.data.split(':')[1]); con=db(); r=con.execute('SELECT * FROM episodes WHERE id=?',(eid,)).fetchone(); con.close()
   if not r: await q.message.reply_text('Episode nahi mila.'); return
   cap=f"🎬 {r['title']}\n📺 Episode {r['episode']}\n🌐 {r['language']} • 🎞 {r['quality']}\n\n✨ Enjoy watching!"
   if r['file_type']=='video': await c.bot.send_video(q.message.chat_id,r['file_id'],caption=cap)
   elif r['file_type']=='audio': await c.bot.send_audio(q.message.chat_id,r['file_id'],caption=cap)
   else: await c.bot.send_document(q.message.chat_id,r['file_id'],caption=cap)
  except Exception: log.exception('Sending episode failed'); await q.message.reply_text('File send nahi ho payi. Bot permissions/file access check karein.')
async def add_cmd(u,c):
 if not await admin_only(u,c): return
 p=[x.strip() for x in ' '.join(c.args).split('|')]
 if len(p)<4: await u.effective_message.reply_text('Format: /add Anime Name | 01 | Hindi | 1080p'); return
 await u.effective_message.reply_text('File ko admin chat mein caption ke saath upload karein; /add metadata-only entries nahi banata. Use caption: '+ ' | '.join(p))
async def stats(u,c):
 if not await admin_only(u,c): return
 con=db(); n=con.execute('SELECT COUNT(*) FROM episodes').fetchone()[0]; users=con.execute('SELECT COUNT(*) FROM users').fetchone()[0]; con.close(); await u.effective_message.reply_text(f'📊 Users: {users}\n🎞 Catalog entries: {n}')
async def source_post(u,c):
 msg=u.channel_post
 if not msg or not SOURCE_CHANNEL_ID or str(msg.chat_id)!=SOURCE_CHANNEL_ID: return
 # Telegram channel updates arrive as channel_post; index only supported media posts.
 if msg.video or msg.document or msg.audio: await handle_video(u,c)
def main():
 if not TOKEN: raise RuntimeError('Set BOT_TOKEN environment variable')
 db().close(); app=Application.builder().token(TOKEN).build()
 app.add_handler(CommandHandler('start',start)); app.add_handler(CommandHandler('help',help_cmd)); app.add_handler(CommandHandler('search',search_cmd)); app.add_handler(CommandHandler('episodes',episodes_cmd)); app.add_handler(CommandHandler('add',add_cmd)); app.add_handler(CommandHandler('stats',stats)); app.add_handler(CommandHandler('admin',admin_panel)); app.add_handler(CommandHandler('settings',admin_panel)); app.add_handler(CommandHandler('admins',admin_panel))
 app.add_handler(CallbackQueryHandler(callbacks)); app.add_handler(MessageHandler(filters.UpdateType.CHANNEL_POST,source_post)); app.add_handler(MessageHandler(filters.VIDEO|filters.Document.ALL|filters.AUDIO,handle_video)); app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND,text_handler))
 log.info('Polling started'); app.run_polling(drop_pending_updates=False)
if __name__ == '__main__': main()
