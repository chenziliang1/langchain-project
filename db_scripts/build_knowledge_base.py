import os
import asyncio
import aiomysql
import aiohttp
from bs4 import BeautifulSoup
import chromadb
from chromadb.utils import embedding_functions
import logging
from dotenv import load_dotenv

# configure log
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
load_dotenv()

# ==========================================
# 1. configurationarguments
# ==========================================
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'db'),
    'port': int(os.getenv('DB_PORT', 3306)),
    'user': 'root',
    'password': os.getenv('DB_PASSWORD', 'rootpassword'),
    'db': os.getenv('DB_NAME', 'gdelt_db'),
    'autocommit': True
}

BATCH_SIZE = 10  
CONCURRENT_LIMIT = 3  # limit concurrent HTTP requests to save memory
UPSERT_CHUNK_SIZE = 2  # process only 2 docs at a time for embedding
# 🎯 willprojectmarkcallbackbig，For example, this time we set a 2000 articlesmallprojectmark
TOTAL_TARGET = 300000 

# newincrease：used forsaveprogressthislocationfile
PROGRESS_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), 'sync_progress.txt'))

def get_last_offset():
    """readuploadonetimeprocesstodatabaserow count"""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return int(f.read().strip())
    return 0

def save_offset(offset):
    """savewhenbeforeprogress"""
    with open(PROGRESS_FILE, 'w') as f:
        f.write(str(offset))

# ==========================================
# 2. corefunctionnumberfixmeaning
# ==========================================
def init_chromadb():
    """initialstartization ChromaDB andtowardamountmodel"""
    logging.info("🚀 initialstartization ChromaDB towardamountdatabase...")
    # confirmsavefreeinprojectrootdirectoryunder chroma_db filefolderin
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../chroma_db'))
    chroma_client = chromadb.PersistentClient(path=db_path)
    
    logging.info("⏳ correctinaddload Embedding model (all-MiniLM-L6-v2)...")
    sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    
    collection = chroma_client.get_or_create_collection(
        name="gdelt_news_collection",
        embedding_function=sentence_transformer_ef
    )
    return collection

async def fetch_urls_batch(pool, limit, offset=0):
    """from MySQL inbatchcapturefetchpackagecontain SOURCEURL eventrecordlog"""
    query = """
        SELECT GlobalEventID, SQLDATE, SOURCEURL 
        FROM events_table 
        WHERE SOURCEURL IS NOT NULL AND SOURCEURL != ''
        ORDER BY GlobalEventID DESC
        LIMIT %s OFFSET %s;
    """
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(query, (limit, offset))
            return await cur.fetchall()

async def scrape_article(session, event_id, date, url, semaphore):
    """asyncFetch single news article content with concurrency limit"""
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    timeout = aiohttp.ClientTimeout(total=10)
    
    async with semaphore:  # limit concurrent requests
        try:
            async with session.get(url, headers=headers, timeout=timeout) as response:
                if response.status == 200:
                    # limit response size to prevent memory explosion (max 5MB)
                    content_length = response.headers.get('Content-Length')
                    if content_length and int(content_length) > 5 * 1024 * 1024:
                        logging.warning(f"⚠️ URL too large ({int(content_length)/1024/1024:.1f}MB), skipping: {url[:80]}...")
                        return None
                    
                    html = await response.text()
                    # double check size after download
                    if len(html) > 5 * 1024 * 1024:
                        logging.warning(f"⚠️ Downloaded content too large ({len(html)/1024/1024:.1f}MB), skipping: {url[:80]}...")
                        return None
                    
                    soup = BeautifulSoup(html, 'html.parser')
                    paragraphs = soup.find_all('p')
                    article_text = ' '.join([p.get_text(strip=True) for p in paragraphs])
                    
                    # Filter out too short useless content and limit length
                    if len(article_text) > 150:
                        # limit text to max 8000 chars to save memory during embedding
                        return {
                            "id": str(event_id),
                            "text": article_text[:8000],
                            "metadata": {"source_url": url, "date": str(date)}
                        }
                return None
        except Exception as e:
            # ignorenetworksuperwhenorfetchfailedchainreceive
            logging.debug(f"fetch failed for {url[:60]}...: {str(e)[:100]}")
            return None

# ==========================================
# 3. mainpipelinecompilearrange (Supports resumable transfer version)
# ==========================================
async def main():
    collection = init_chromadb()
    pool = await aiomysql.create_pool(**DB_CONFIG)
    
    # create semaphore limit concurrent HTTP requests
    semaphore = asyncio.Semaphore(CONCURRENT_LIMIT)
    
    total_processed = 0
    total_saved = 0
    
    # 🌟 corechangeactivate：fromfileinreaduploadtimeprogress
    current_offset = get_last_offset()
    logging.info(f"🔄 detecttohistoryprogress，thistimewillfromdatabaseNo. {current_offset} rowstartfetch。")
    
    try:
        async with aiohttp.ClientSession() as session:
            while total_saved < TOTAL_TARGET:
                logging.info(f"\n📦 correctinfromdatabasepullfetchNo. {current_offset} to {current_offset + BATCH_SIZE} itemrecordlog...")
                records = await fetch_urls_batch(pool, BATCH_SIZE, current_offset)
                
                if not records:
                    logging.info("databaseinnohasupdatemultirecordlogdone，all URL alreadyprocesscompletefinish！")
                    break
                
                # createandsendfetchtask (with concurrency limit)
                logging.info(f"   Processing {len(records)} URLs with max {CONCURRENT_LIMIT} concurrent requests...")
                tasks = [scrape_article(session, r['GlobalEventID'], r['SQLDATE'], r['SOURCEURL'], semaphore) for r in records]
                scraped_results = await asyncio.gather(*tasks)
                
                valid_docs = [res for res in scraped_results if res is not None]
                
                if valid_docs:
                    # process in smaller chunks to avoid memory spike during embedding
                    import gc
                    for i in range(0, len(valid_docs), UPSERT_CHUNK_SIZE):
                        chunk = valid_docs[i:i + UPSERT_CHUNK_SIZE]
                        ids = [doc['id'] for doc in chunk]
                        texts = [doc['text'][:5000] for doc in chunk]  # limit text length to 5000 chars
                        metadatas = [doc['metadata'] for doc in chunk]
                        
                        logging.info(f"   Embedding chunk {i//UPSERT_CHUNK_SIZE + 1}/{(len(valid_docs)-1)//UPSERT_CHUNK_SIZE + 1} ({len(chunk)} docs)...")
                        collection.upsert(documents=texts, metadatas=metadatas, ids=ids)
                        total_saved += len(chunk)
                        
                        # force garbage collection after each chunk
                        gc.collect()
                    
                    logging.info(f"✅ batchcompleted！successfetchandvectorize {len(valid_docs)} articlefilechapter。(Cumulative storage for this run: {total_saved}/{TOTAL_TARGET})")
                else:
                    logging.warning("⚠️ thisbatchallchainreceivefetchfailed，continueunderonebatch。")
                
                total_processed += len(records)
                current_offset += BATCH_SIZE
                
                # 🌟 corechangeactivate：eachcompletedonebatch，justsaveonetimeprogress
                save_offset(current_offset)

    finally:
        pool.close()
        await pool.wait_closed()
        logging.info(f"🎉 taskend！thistimetotalprocesschainreceive: {total_processed}，successinputlibraryfilethis: {total_saved} article。mostnew Offset alreadysavefor {current_offset}。")

if __name__ == "__main__":
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())