#!/usr/bin/env python3
"""
GDELT parallel ETL Pipeline
Purpose: parallel process multi-date data，pre-calculate all statistics tables
Features: 
    - full process（no LIMIT restriction）
    - multi-date parallel（each date independent worker）
    - batch insert optimization

Usage:
    python db_scripts/parallel_etl_pipeline.py --start 2024-01-01 --end 2024-12-31 --workers 8
    python db_scripts/parallel_etl_pipeline.py --date-file dates.txt --workers 4
    python db_scripts/parallel_etl_pipeline.py --missing-only --workers 8
"""

import argparse
import asyncio
import json
import logging
import os
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# add project path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.database.pool import DatabasePool

# configure log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(process)d - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/tmp/gdelt_parallel_etl.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class GDELTETLWorker:
    """ETL work unit（each date one instance）"""
    
    def __init__(self, date: str):
        self.date = date
        self.pool: Optional[DatabasePool] = None
        
    async def initialize(self):
        """initialize database connection"""
        self.pool = await DatabasePool.initialize()
        
    async def close(self):
        """close connection"""
        await DatabasePool.close()
        
    async def run_etl(self) -> Dict:
        """run full ETL process"""
        result = {
            'date': self.date,
            'status': 'success',
            'steps': {},
            'error': None
        }
        
        try:
            await self.initialize()
            
            # 1. check data
            has_data = await self._check_data_exists()
            if not has_data:
                result['status'] = 'skipped'
                result['error'] = 'no data'
                return result
            
            # 2. generate daily digest
            summary_count = await self._generate_daily_summary()
            result['steps']['daily_summary'] = summary_count
            
            # 3. generate event fingerprints（allamount）
            fingerprint_count = await self._generate_event_fingerprints()
            result['steps']['fingerprints'] = fingerprint_count
            
            # 4. update region statistics
            region_count = await self._update_region_stats()
            result['steps']['region_stats'] = region_count
            
            # 5. update geo grid
            grid_count = await self._update_geo_grid()
            result['steps']['geo_grid'] = grid_count
            
            # 6. identify hot events
            hot_count = await self._identify_hot_events()
            result['steps']['hot_events'] = hot_count
            
            logger.info(f"✅ [{self.date}] ETL completed: {result['steps']}")
            
        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)
            logger.error(f"❌ [{self.date}] ETL failed: {e}", exc_info=True)
        finally:
            await self.close()
            
        return result
    
    async def _check_data_exists(self) -> bool:
        """checkfingerfixdatewhetherhasdata"""
        result = await self.pool.fetchone(
            "SELECT COUNT(*) as cnt FROM events_table WHERE SQLDATE = %s",
            (self.date,)
        )
        count = result['cnt'] if result else 0
        if count > 0:
            logger.info(f"📊 [{self.date}] dataamount: {count} item")
        return count > 0
    
    async def _generate_daily_summary(self) -> int:
        """generate daily digesttable"""
        logger.info(f"📊 [{self.date}] generatedayreport")
        
        # statisticsbasicdata
        stats = await self.pool.fetchone("""
            SELECT 
                COUNT(*) as total_events,
                SUM(CASE WHEN GoldsteinScale < -5 THEN 1 ELSE 0 END) as conflict_events,
                SUM(CASE WHEN GoldsteinScale > 5 THEN 1 ELSE 0 END) as cooperation_events,
                AVG(GoldsteinScale) as avg_goldstein,
                AVG(AvgTone) as avg_tone
            FROM events_table
            WHERE SQLDATE = %s
        """, (self.date,))
        
        if not stats or stats['total_events'] == 0:
            logger.warning(f"  ⚠️ [{self.date}] no data")
            return 0
        
        # fetchTop Actor
        actors_result = await self.pool.fetchall("""
            SELECT Actor1Name as name, COUNT(*) as cnt
            FROM events_table
            WHERE SQLDATE = %s AND Actor1Name != '' AND Actor1Name IS NOT NULL
            GROUP BY Actor1Name
            ORDER BY cnt DESC
            LIMIT 10
        """, (self.date,))
        top_actors = [{"name": row['name'], "count": row['cnt']} for row in actors_result]
        
        # fetchTop Location
        locations_result = await self.pool.fetchall("""
            SELECT ActionGeo_FullName as name, COUNT(*) as cnt
            FROM events_table
            WHERE SQLDATE = %s AND ActionGeo_FullName IS NOT NULL AND ActionGeo_FullName != ''
            GROUP BY ActionGeo_FullName
            ORDER BY cnt DESC
            LIMIT 10
        """, (self.date,))
        top_locations = [{"name": row['name'], "count": row['cnt']} for row in locations_result]
        
        # eventtypedistribution
        types_result = await self.pool.fetchall("""
            SELECT 
                CASE 
                    WHEN EventRootCode = '01' THEN 'statement'
                    WHEN EventRootCode = '02' THEN 'appeal'
                    WHEN EventRootCode = '03' THEN 'intent'
                    WHEN EventRootCode IN ('04', '05') THEN 'consult'
                    WHEN EventRootCode = '06' THEN 'material'
                    WHEN EventRootCode IN ('07', '08') THEN 'aid'
                    WHEN EventRootCode = '09' THEN 'yield'
                    WHEN EventRootCode = '10' THEN 'demand'
                    WHEN EventRootCode = '11' THEN 'disapprove'
                    WHEN EventRootCode = '12' THEN 'reject'
                    WHEN EventRootCode = '13' THEN 'threaten'
                    WHEN EventRootCode = '14' THEN 'protest'
                    WHEN EventRootCode = '15' THEN 'force'
                    WHEN EventRootCode IN ('16', '17') THEN 'coerce'
                    WHEN EventRootCode IN ('18', '19', '20') THEN 'fight'
                    ELSE 'other'
                END as event_type,
                COUNT(*) as cnt
            FROM events_table
            WHERE SQLDATE = %s
            GROUP BY event_type
            ORDER BY cnt DESC
        """, (self.date,))
        type_dist = {row['event_type']: row['cnt'] for row in types_result}
        
        # hoteventfingerprint（temporarywhenuseGID，aftercontinueupdateforfingerprint）
        hot_result = await self.pool.fetchall("""
            SELECT GlobalEventID, NumArticles * ABS(GoldsteinScale) as hot_score
            FROM events_table
            WHERE SQLDATE = %s
            ORDER BY hot_score DESC
            LIMIT 20
        """, (self.date,))
        hot_events = [str(row['GlobalEventID']) for row in hot_result]
        
        # insert/updatedayreport
        await self.pool.execute("""
            INSERT INTO daily_summary 
            (date, total_events, conflict_events, cooperation_events,
             avg_goldstein, avg_tone, top_actors, top_locations,
             event_type_distribution, hot_event_fingerprints)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            total_events = VALUES(total_events),
            conflict_events = VALUES(conflict_events),
            cooperation_events = VALUES(cooperation_events),
            avg_goldstein = VALUES(avg_goldstein),
            avg_tone = VALUES(avg_tone),
            top_actors = VALUES(top_actors),
            top_locations = VALUES(top_locations),
            event_type_distribution = VALUES(event_type_distribution),
            hot_event_fingerprints = VALUES(hot_event_fingerprints)
        """, (
            self.date, 
            stats['total_events'], 
            stats['conflict_events'] or 0, 
            stats['cooperation_events'] or 0,
            stats['avg_goldstein'], 
            stats['avg_tone'],
            json.dumps(top_actors),
            json.dumps(top_locations),
            json.dumps(type_dist),
            json.dumps(hot_events)
        ))
        
        logger.info(f"  ✓ [{self.date}] dayreport: {stats['total_events']} event")
        return stats['total_events']
    
    async def _generate_event_fingerprints(self) -> int:
        """forneweventgeneratefingerprint（full process，no LIMIT）"""
        logger.info(f"🔖 [{self.date}] generate event fingerprints")
        
        total_processed = 0
        batch_size = 5000
        offset = 0
        
        # firstfetchalreadyexistfingerprint（avoid LEFT JOIN transactionisolationquestion）
        existing = await self.pool.fetchall(
            "SELECT global_event_id FROM event_fingerprints WHERE generated_at >= DATE_SUB(NOW(), INTERVAL 1 DAY)",
        )
        existing_gids = {row['global_event_id'] for row in existing}
        
        while True:
            batch = await self.pool.fetchall("""
                SELECT GlobalEventID, SQLDATE, Actor1Name, Actor2Name,
                       EventCode, EventRootCode, GoldsteinScale,
                       ActionGeo_FullName, ActionGeo_CountryCode,
                       ActionGeo_Lat, ActionGeo_Long, NumArticles
                FROM events_table
                WHERE SQLDATE = %s
                ORDER BY GlobalEventID
                LIMIT %s OFFSET %s
            """, (self.date, batch_size, offset))
            
            if not batch:
                break
            
            fingerprints = []
            for evt in batch:
                gid = evt['GlobalEventID']
                if gid in existing_gids:
                    continue
                fp_data = self._create_fingerprint(evt)
                fingerprints.append(fp_data)
                existing_gids.add(gid)
            
            if fingerprints:
                inserted = await self._batch_insert_fingerprints(fingerprints)
                total_processed += inserted
                logger.info(f"  ✓ [{self.date}] batch: +{inserted}, tiredplan {total_processed}")
            
            offset += len(batch)
            if len(batch) < batch_size:
                break
        
        logger.info(f"  ✓ [{self.date}] fingerprinttotal: {total_processed}")
        return total_processed
    
    def _create_fingerprint(self, evt: Dict) -> Tuple:
        """foreventcreatefingerprint"""
        gid = evt['GlobalEventID']
        sqldate = evt['SQLDATE']
        actor1 = evt['Actor1Name'] or 'some country'
        actor2 = evt['Actor2Name'] or 'objectmethod'
        event_root = str(evt['EventRootCode'] or '')[:2]
        goldstein = evt['GoldsteinScale'] or 0
        location = evt['ActionGeo_FullName'] or 'unknownlocationpoint'
        country = evt['ActionGeo_CountryCode'] or 'XX'
        articles = evt['NumArticles'] or 0
        
        # parsedate
        if isinstance(sqldate, str):
            date_str = sqldate.replace('-', '')
        else:
            date_str = str(sqldate).replace('-', '')
        
        # locationpointshrinkwrite
        location_code = 'UNK'
        if location and location != 'unknownlocationpoint':
            parts = location.split(',')
            if parts:
                location_code = parts[0].strip()[:3].upper()
        
        # eventtype
        type_map = {
            '01': 'STATEMENT', '02': 'APPEAL', '03': 'INTENT',
            '04': 'CONSULT', '05': 'ENGAGE', '06': 'AID',
            '07': 'AID', '08': 'AID', '09': 'YIELD',
            '10': 'DEMAND', '11': 'DISAPPROVE', '12': 'REJECT',
            '13': 'THREATEN', '14': 'PROTEST', '15': 'FORCE',
            '16': 'REDUCE', '17': 'COERCE', '18': 'FIGHT',
            '19': 'MASS', '20': 'ASSAULT'
        }
        event_type = type_map.get(event_root, 'EVENT')
        
        # usecomplete GID guaranteefingerprint onlyone
        seq = str(gid)
        fingerprint = f"{country}-{date_str}-{location_code}-{event_type}-{seq}"
        
        # generateinsidecontent
        headline = self._generate_headline(actor1, actor2, event_root, location)
        summary = self._generate_summary(actor1, actor2, location, goldstein, articles)
        key_actors = json.dumps([a for a in [actor1, actor2] if a and a not in ['some country', 'objectmethod']])
        event_label = self._get_event_label(event_root)
        severity = min(10, max(1, abs(goldstein) * 2))
        if articles > 100:
            severity += 1
        severity = min(10, severity)
        
        return (
            gid, fingerprint, headline, summary,
            key_actors, event_label, severity,
            location, country
        )
    
    def _generate_headline(self, actor1: str, actor2: str, 
                          event_root: str, location: str) -> str:
        """generateeventmarktopic"""
        a1 = actor1 or 'some country'
        a2 = actor2 or 'objectmethod'
        loc = location or 'somelocation'
        
        action_map = {
            '01': f"{a1}sendtablesoundclear", '02': f"{a1}toward{a2}appeal",
            '03': f"{a1}tablereachideagraph", '04': f"{a1}and{a2}consultbusiness",
            '05': f"{a1}paramand{a2}affair", '06': f"{a1}toward{a2}provideoffersupplies",
            '07': f"{a1}toward{a2}provide aid", '08': f"{a1}toward{a2}provide aid",
            '09': f"{a1}toward{a2}letstep", '10': f"{a1}toward{a2}provideoutputwantrequest",
            '11': f"{a1}object{a2}tableshownotfull", '12': f"{a1}reject{a2}",
            '13': f"{a1}threat{a2}", '14': f"{a1}sendstartprotest",
            '15': f"{a1}expandshowforce", '16': f"{a1}reduceobject{a2}relationship",
            '17': f"{a1}coerce{a2}", '18': f"{a1}and{a2}occurfriction",
            '19': f"{a1}and{a2}occurconflict", '20': f"{a1}object{a2}useforce"
        }
        
        action = action_map.get(event_root, f"{a1}and{a2}interaction")
        if loc and loc not in [a1, a2]:
            return f"{action} ({loc})"
        return action
    
    def _generate_summary(self, actor1: str, actor2: str, 
                         location: str, goldstein: float, articles: int) -> str:
        """generateeventdigest"""
        a1 = actor1 or 'some country'
        a2 = actor2 or 'objectmethod'
        loc = location or 'somelocation'
        
        intensity = "slight"
        if goldstein:
            if abs(goldstein) > 7:
                intensity = "serious"
            elif abs(goldstein) > 4:
                intensity = "inetc"
        
        coverage = ""
        if articles > 100:
            coverage = f"，receivewidespreadreport({articles}article)"
        elif articles > 10:
            coverage = f"，receivecertainreport({articles}article)"
        
        return f"{a1}and{a2}in{loc}occur{intensity}interaction{coverage}。"
    
    def _get_event_label(self, event_root: str) -> str:
        """fetcheventtypetag"""
        labels = {
            '01': 'outsidehandsoundclear', '02': 'outsidehandappeal', '03': 'policyideatoward',
            '04': 'outsidehandconsultbusiness', '05': 'paramandcombinejob', '06': 'suppliesaid',
            '07': 'personnelaid', '08': 'protectaid', '09': 'letstepslowand',
            '10': 'provideoutputwantrequest', '11': 'tablereachnotfull', '12': 'rejectantiobject',
            '13': 'threatwarning', '14': 'protestshowthreat', '15': 'expandshowforce',
            '16': 'relationshipdowngrade', '17': 'strongsystemcoerce', '18': 'militaryfriction',
            '19': 'bigrulemodelconflict', '20': 'militaryinstallattack'
        }
        return labels.get(event_root, 'otherevent')
    
    async def _batch_insert_fingerprints(self, fingerprints: List[Tuple]) -> int:
        """
        batchinsertfingerprint（use INSERT IGNORE，nodeadlock，rowcount accurate）
        
        strategy：INSERT IGNORE meettoduplicatekeydirectignore，returnbackrealborderinsertrow count
        avoiduse ON DUPLICATE KEY UPDATE（cancantouchsenddeadlock）
        
        Args:
            fingerprints: fingerprintdatacolumntable，eachitemyes 9 charactersegment tuple
            
        Returns:
            successinsertrow count
        """
        if not fingerprints:
            return 0
        
        try:
            async with self.pool._pool.acquire() as conn:
                async with conn.cursor() as cursor:
                    # closeMySQL Warningtransportoutput，avoidDuplicate刷屏
                    await cursor.execute("SET sql_notes = 0")
                    # INSERT IGNORE：duplicateruleignore，rowcount accurate
                    await cursor.executemany("""
                        INSERT IGNORE INTO event_fingerprints 
                        (global_event_id, fingerprint, headline, summary, 
                         key_actors, event_type_label, severity_score,
                         location_name, location_country)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, fingerprints)
                    await conn.commit()
                    # cursor.rowcount objectat INSERT IGNORE yesaccurate
                    return cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0
                    
        except Exception as e:
            # rarecaseunderbatchfailed，downgradeexpelitem
            logger.warning(f"    [{self.date}] batchinsertfailed，downgradeexpelitem: {e}")
            inserted = 0
            for fp_data in fingerprints:
                try:
                    await self.pool.execute("""
                        INSERT IGNORE INTO event_fingerprints 
                        (global_event_id, fingerprint, headline, summary, 
                         key_actors, event_type_label, severity_score,
                         location_name, location_country)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, fp_data)
                    inserted += 1
                except Exception:
                    pass  # ignoreformitemerror
            return inserted
    
    async def _update_region_stats(self) -> int:
        """update region statistics"""
        logger.info(f"🌍 [{self.date}] update region statistics")
        
        regions = await self.pool.fetchall("""
            SELECT 
                ActionGeo_CountryCode as region,
                MAX(ActionGeo_FullName) as region_name,
                COUNT(*) as event_count,
                AVG(CASE WHEN GoldsteinScale < 0 THEN ABS(GoldsteinScale) ELSE 0 END) as conflict_intensity,
                AVG(CASE WHEN GoldsteinScale > 0 THEN GoldsteinScale ELSE 0 END) as cooperation_intensity,
                AVG(AvgTone) as avg_tone,
                MAX(Actor1Name) as primary_actor
            FROM events_table
            WHERE SQLDATE = %s AND ActionGeo_CountryCode IS NOT NULL AND ActionGeo_CountryCode != ''
            GROUP BY ActionGeo_CountryCode
            HAVING event_count > 10
        """, (self.date,))
        
        updated = 0
        for r in regions:
            actors = json.dumps([r['primary_actor']]) if r['primary_actor'] else '[]'
            try:
                await self.pool.execute("""
                    INSERT INTO region_daily_stats
                    (region_code, region_name, region_type, date, event_count,
                     conflict_intensity, cooperation_intensity, avg_tone, primary_actors)
                    VALUES (%s, %s, 'country', %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    event_count = VALUES(event_count),
                    conflict_intensity = VALUES(conflict_intensity),
                    cooperation_intensity = VALUES(cooperation_intensity),
                    avg_tone = VALUES(avg_tone),
                    primary_actors = VALUES(primary_actors)
                """, (
                    r['region'], r['region_name'][:100], self.date, 
                    r['event_count'], r['conflict_intensity'], 
                    r['cooperation_intensity'], r['avg_tone'], actors
                ))
                updated += 1
            except Exception as e:
                logger.warning(f"    [{self.date}] skiplocationarea {r['region']}: {e}")
        
        logger.info(f"  ✓ [{self.date}] update {updated} locationarea")
        return updated
    
    async def _update_geo_grid(self) -> int:
        """update geo gridhot"""
        logger.info(f"🗺️ [{self.date}] update geo grid")
        
        grids = await self.pool.fetchall("""
            SELECT 
                FLOOR(ActionGeo_Lat * 2) / 2 as lat_grid,
                FLOOR(ActionGeo_Long * 2) / 2 as lng_grid,
                COUNT(*) as event_count,
                SUM(CASE WHEN GoldsteinScale < -5 THEN 1 ELSE 0 END) as conflict_sum,
                AVG(GoldsteinScale) as avg_goldstein,
                AVG(AvgTone) as avg_tone
            FROM events_table
            WHERE SQLDATE = %s 
              AND ActionGeo_Lat IS NOT NULL 
              AND ActionGeo_Long IS NOT NULL
              AND ActionGeo_Lat != 0
              AND ActionGeo_Long != 0
            GROUP BY lat_grid, lng_grid
            HAVING event_count > 5
        """, (self.date,))
        
        updated = 0
        for g in grids:
            grid_id = f"LAT_{g['lat_grid']}_LNG_{g['lng_grid']}"
            try:
                await self.pool.execute("""
                    INSERT INTO geo_heatmap_grid
                    (grid_id, lat_grid, lng_grid, date, event_count, 
                     conflict_sum, avg_goldstein, avg_tone)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                    event_count = VALUES(event_count),
                    conflict_sum = VALUES(conflict_sum),
                    avg_goldstein = VALUES(avg_goldstein),
                    avg_tone = VALUES(avg_tone)
                """, (
                    grid_id, g['lat_grid'], g['lng_grid'], self.date,
                    g['event_count'], g['conflict_sum'], 
                    g['avg_goldstein'], g['avg_tone']
                ))
                updated += 1
            except Exception as e:
                logger.warning(f"    [{self.date}] skipgrid {grid_id}: {e}")
        
        logger.info(f"  ✓ [{self.date}] update {updated} grid")
        return updated
    
    async def _identify_hot_events(self) -> int:
        """recognizeandupdatehoteventfingerprintreference"""
        logger.info(f"🔥 [{self.date}] identify hot events")
        
        result = await self.pool.fetchone("""
            SELECT hot_event_fingerprints 
            FROM daily_summary 
            WHERE date = %s
        """, (self.date,))
        
        if not result or not result['hot_event_fingerprints']:
            logger.info(f"  ⚠️ [{self.date}] nohoteventdata")
            return 0
        
        hot_data = result['hot_event_fingerprints']
        if isinstance(hot_data, str):
            gids = json.loads(hot_data)
        else:
            gids = hot_data
        
        # willGIDconvertforfingerprint
        fingerprints = []
        for gid in gids[:10]:
            fp_result = await self.pool.fetchone("""
                SELECT fingerprint FROM event_fingerprints 
                WHERE global_event_id = %s
            """, (gid,))
            if fp_result:
                fingerprints.append(fp_result['fingerprint'])
        
        # updatedayreport
        if fingerprints:
            await self.pool.execute("""
                UPDATE daily_summary 
                SET hot_event_fingerprints = %s 
                WHERE date = %s
            """, (json.dumps(fingerprints), self.date))
            logger.info(f"  ✓ [{self.date}] update {len(fingerprints)} hoteventfingerprint")
        
        return len(fingerprints)


async def run_etl_for_date(date: str) -> Dict:
    """forformdaterun ETL（used forparallelexecrow）"""
    worker = GDELTETLWorker(date)
    return await worker.run_etl()


def run_etl_sync(date: str) -> Dict:
    """syncpackageinstallhandler（used for ProcessPoolExecutor）"""
    return asyncio.run(run_etl_for_date(date))


class ParallelETLPipeline:
    """parallel ETL pipelinemanager"""
    
    def __init__(self, workers: int = 4):
        self.workers = workers
        self.results: List[Dict] = []
        
    def get_date_range(self, start: str, end: str) -> List[str]:
        """generatedatecolumntable"""
        dates = []
        current = datetime.strptime(start, '%Y-%m-%d')
        end_date = datetime.strptime(end, '%Y-%m-%d')
        
        while current <= end_date:
            dates.append(current.strftime('%Y-%m-%d'))
            current += timedelta(days=1)
        
        return dates
    
    def get_dates_from_file(self, filepath: str) -> List[str]:
        """fromfilereaddatecolumntable"""
        dates = []
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    dates.append(line)
        return dates
    
    async def get_missing_dates(self) -> List[str]:
        """fetchneedprocessdate（baseatfingerprintoverriderate）"""
        pool = await DatabasePool.initialize()
        try:
            # findoverrideratelowat 90% date
            result = await pool.fetchall("""
                SELECT 
                    e.SQLDATE as date,
                    COUNT(DISTINCT e.GlobalEventID) as total_events,
                    COUNT(DISTINCT f.global_event_id) as has_fingerprint
                FROM events_table e
                LEFT JOIN event_fingerprints f ON e.GlobalEventID = f.global_event_id
                GROUP BY e.SQLDATE
                HAVING has_fingerprint / total_events < 0.9 OR has_fingerprint IS NULL
                ORDER BY e.SQLDATE
            """)
            
            dates = [str(r['date']) for r in result]
            logger.info(f"📋 sendnow {len(dates)} needprocessdate")
            return dates
        finally:
            await DatabasePool.close()
    
    def run_parallel(self, dates: List[str]):
        """parallelrun ETL"""
        logger.info(f"🚀 startparallel ETL: {len(dates)} date, {self.workers}  worker")
        
        completed = 0
        failed = 0
        skipped = 0
        
        with ProcessPoolExecutor(max_workers=self.workers) as executor:
            # commitalltask
            future_to_date = {
                executor.submit(run_etl_sync, date): date 
                for date in dates
            }
            
            # processresultresult
            for future in as_completed(future_to_date):
                date = future_to_date[future]
                try:
                    result = future.result()
                    self.results.append(result)
                    
                    if result['status'] == 'success':
                        completed += 1
                        logger.info(f"✅ [{date}] completed: {result['steps']}")
                    elif result['status'] == 'skipped':
                        skipped += 1
                        logger.info(f"⏭️  [{date}] skip: {result['error']}")
                    else:
                        failed += 1
                        logger.error(f"❌ [{date}] failed: {result['error']}")
                        
                except Exception as e:
                    failed += 1
                    logger.error(f"❌ [{date}] asyncconstant: {e}")
                
                # progressreportwarn
                total = len(dates)
                processed = completed + failed + skipped
                if processed % 10 == 0 or processed == total:
                    logger.info(f"📊 progress: {processed}/{total} ({processed/total*100:.1f}%) | "
                              f"success: {completed} | failed: {failed} | skip: {skipped}")
        
        # mostendreportwarn
        logger.info("=" * 60)
        logger.info("📊 ETL completedreportwarn")
        logger.info(f"   total: {len(dates)}")
        logger.info(f"   success: {completed}")
        logger.info(f"   failed: {failed}")
        logger.info(f"   skip: {skipped}")
        
        # statisticsfingerprintgenerate
        total_fingerprints = sum(
            r['steps'].get('fingerprints', 0) 
            for r in self.results 
            if r['status'] == 'success'
        )
        logger.info(f"   totalfingerprint: {total_fingerprints}")
        logger.info("=" * 60)
        
        return self.results


def main():
    parser = argparse.ArgumentParser(description='GDELT parallel ETL Pipeline')
    parser.add_argument('--start', help='startdate (YYYY-MM-DD)')
    parser.add_argument('--end', help='enddate (YYYY-MM-DD)')
    parser.add_argument('--date-file', help='datecolumntablefile')
    parser.add_argument('--workers', type=int, default=4, help='parallel worker number (default: 4)')
    parser.add_argument('--missing-only', action='store_true', help='onlyprocesslackfailfingerprintdate')
    parser.add_argument('--dry-run', action='store_true', help='onlycheck，notexecrow')
    
    args = parser.parse_args()
    
    pipeline = ParallelETLPipeline(workers=args.workers)
    
    # fetchdatecolumntable
    if args.missing_only:
        dates = asyncio.run(pipeline.get_missing_dates())
    elif args.date_file:
        dates = pipeline.get_dates_from_file(args.date_file)
    elif args.start and args.end:
        dates = pipeline.get_date_range(args.start, args.end)
    else:
        parser.print_help()
        sys.exit(1)
    
    if not dates:
        logger.info("📋 nohasneedprocessdate")
        return
    
    logger.info(f"📋 planplanprocess {len(dates)} date")
    
    if args.dry_run:
        logger.info("🔍 dryrunmodelpattern，onlyprintdatecolumntable:")
        for d in dates[:10]:
            logger.info(f"   - {d}")
        if len(dates) > 10:
            logger.info(f"   ... stillhas {len(dates)-10} ")
        return
    
    # parallelrun
    pipeline.run_parallel(dates)


if __name__ == "__main__":
    main()
