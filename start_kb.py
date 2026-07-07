import subprocess
import time
import sys
import logging

# Configurationlogtransportoutput
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')

def run_knowledge_base_builder():
    """
    runrow Docker contenthandlerincrawlerandvectorizepipeline。
    ifmeettononnormalExit（ifnetworkinbreak），Will auto-restart to continue fetching。
    """
    command = ["docker-compose", "run", "--rm", "app", "python", "db_scripts/build_knowledge_base.py"]
    
    retry_count = 0
    max_retries = 50  # SetA maximum consecutive restart count，preventstopinfinite loop
    
    logging.info("🚀 Start knowledge base build daemon (Daemon Mode)...")
    logging.info("💡 Hint: followwhenbyunder Ctrl+C Can safely terminate the entire process。")
    print("=" * 60)
    
    while retry_count < max_retries:
        try:
            # start Docker command，andwilltransportoutputreal-timeprinttoendend
            process = subprocess.Popen(command)
            
            # etc.waitenterprocessresultend
            process.wait()
            
            # CheckExitstatusstatecode
            if process.returncode == 0:
                logging.info("🎉 Knowledge base build scriptnormalexecrowcompletefinish！(reachtoprojectmarkoralreadyno data)")
                break
            else:
                retry_count += 1
                logging.warning(f"⚠️ footthisexceptionExit (Returnscode: {process.returncode})。cancanisnetworkwaveactivate。")
                logging.info(f"⏳ correctinenterrowNo. {retry_count} timeautorestart，5secondaftercontinuereceiveforce...")
                time.sleep(5)
                print("-" * 60)
                
        except KeyboardInterrupt:
            # catchcaptureuseuser Ctrl+C strongsystemExit
            logging.info("\n🛑 accepttoinbreakinfoNo.！correctinsafeallExitdaemon process...")
            process.terminate()
            break
        except Exception as e:
            logging.error(f"❌ start Docker commandwhenoccurunknownerror: {e}")
            break

if __name__ == "__main__":
    run_knowledge_base_builder()