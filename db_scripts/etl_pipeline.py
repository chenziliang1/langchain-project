#!/usr/bin/env python3
"""
GDELT ETL Pipeline
Purpose: precalculatedayreportdata、generate event fingerprints、updatestatisticsdata
runfrequency: eachdayonetime（builddiscussearly morning2point）

Usage:
    python db_scripts/etl_pipeline.py [YYYY-MM-DD]
    
    nottransmitargumentsruleprocessyesterdaydaydata
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# add project path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from backend.database.pool import DatabasePool

# configure log
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('/tmp/gdelt_etl.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class GDELTETLPipeline:
    """GDELTdataETLpipeline"""
    
    def __init__(self):
        self.pool: Optional[DatabasePool] = None
        
    async def initialize(self):
        """initialize database connection"""
        self.pool = await DatabasePool.initialize()
        logger.info("✅ databaseconnectionpoolalreadyinitialstartization")
    
    async def close(self):
        """close connection"""
        await DatabasePool.close()
        logger.info("✅ databaseconnectionalreadyclose")
    
    async def run_daily_etl(self, target_date: Optional[str] = None):
        """
        runeachdayETLtask
        
        Args:
            target_date: projectmarkdate (YYYY-MM-DD)，defaultyesterdayday
        """
        if target_date is None:
            target_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        
        logger.info(f"🚀 startETLprocess: {target_date}")
        
        try:
            # 1. checkthisdatewhetherhasdata
            has_data = await self._check_data_exists(target_date)
            if not has_data:
                logger.warning(f"⚠️ {target_date} no data，skipETL")
                return
            
            # 2. generate daily digest
            await self._generate_daily_summary(target_date)
            
            # 3. generateneweventfingerprint
            await self._generate_event_fingerprints(target_date)
            
            # 4. update region statistics
            await self._update_region_stats(target_date)
            
            # 5. update geo grid
            await self._update_geo_grid(target_date)
            
            # 6. identify hot eventsandupdatefingerprintreference
            await self._identify_hot_events(target_date)
            
            logger.info(f"✅ ETLcompleted: {target_date}")
            
        except Exception as e:
            logger.error(f"❌ ETLfailed: {e}", exc_info=True)
            raise
    
    async def _check_data_exists(self, date: str) -> bool:
        """checkfingerfixdatewhetherhasdata"""
        result = await self.pool.fetchone(
            "SELECT COUNT(*) as cnt FROM events_table WHERE SQLDATE = %s",
            (date,)
        )
        count = result['cnt'] if result else 0
        logger.info(f"📊 {date} dataamount: {count} item")
        return count > 0
    
    async def _generate_daily_summary(self, date: str):
        """generate daily digesttable"""
        logger.info(f"📊 generatedayreport: {date}")
        
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
        """, (date,))
        
        if not stats or stats['total_events'] == 0:
            logger.warning(f"  ⚠️ {date} no data")
            return
        
        # fetchTop Actor
        actors_result = await self.pool.fetchall("""
            SELECT Actor1Name as name, COUNT(*) as cnt
            FROM events_table
            WHERE SQLDATE = %s AND Actor1Name != '' AND Actor1Name IS NOT NULL
            GROUP BY Actor1Name
            ORDER BY cnt DESC
            LIMIT 10
        """, (date,))
        
        top_actors = [{"name": row['name'], "count": row['cnt']} for row in actors_result]
        
        # fetchTop Location
        locations_result = await self.pool.fetchall("""
            SELECT ActionGeo_FullName as name, COUNT(*) as cnt
            FROM events_table
            WHERE SQLDATE = %s AND ActionGeo_FullName IS NOT NULL AND ActionGeo_FullName != ''
            GROUP BY ActionGeo_FullName
            ORDER BY cnt DESC
            LIMIT 10
        """, (date,))
        
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
        """, (date,))
        
        type_dist = {row['event_type']: row['cnt'] for row in types_result}
        
        # hoteventfingerprint（temporarywhenuseGID，aftercontinueupdateforfingerprint）
        hot_result = await self.pool.fetchall("""
            SELECT GlobalEventID, NumArticles * ABS(GoldsteinScale) as hot_score
            FROM events_table
            WHERE SQLDATE = %s
            ORDER BY hot_score DESC
            LIMIT 20
        """, (date,))
        
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
            date, 
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
        
        logger.info(f"  ✓ dayreportalreadygenerate: {stats['total_events']} event, {len(top_actors)} activeActor")
    
    async def _generate_event_fingerprints(self, date: str):
        """forneweventgeneratefingerprint"""
        logger.info(f"🔖 generate event fingerprints: {date}")
        
        # fetchwhendaystillnotgeneratefingerprintevent（batchprocess）
        total_processed = 0
        batch_size = 5000
        
        while True:
            batch = await self.pool.fetchall("""
                SELECT e.GlobalEventID, e.SQLDATE, e.Actor1Name, e.Actor2Name,
                       e.EventCode, e.EventRootCode, e.GoldsteinScale,
                       e.ActionGeo_FullName, e.ActionGeo_CountryCode,
                       e.ActionGeo_Lat, e.ActionGeo_Long, e.NumArticles
                FROM events_table e
                LEFT JOIN event_fingerprints f ON e.GlobalEventID = f.global_event_id
                WHERE e.SQLDATE = %s AND f.global_event_id IS NULL
                LIMIT %s
            """, (date, batch_size))
            
            if not batch:
                break
                
            # batchgeneratefingerprint
            fingerprints = []
            for evt in batch:
                fp = self._create_fingerprint(evt)
                fingerprints.append(fp)
            
            # batchinsert
            inserted = 0
            for fp_data in fingerprints:
                try:
                    await self.pool.execute("""
                        INSERT INTO event_fingerprints 
                        (global_event_id, fingerprint, headline, summary, 
                         key_actors, event_type_label, severity_score,
                         location_name, location_country)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                        fingerprint = VALUES(fingerprint)
                    """, fp_data)
                    inserted += 1
                except Exception as e:
                    logger.warning(f"    skipduplicatefingerprint: {e}")
            
            total_processed += inserted
            logger.info(f"  ✓ thisbatchgenerate {inserted} fingerprint，tiredplan {total_processed}")
            
            # ifthisbatchinsufficient batch_size，descriptionprocesscompletedone
            if len(batch) < batch_size:
                break
        
        logger.info(f"  ✓ totaltotalgenerate {total_processed} fingerprint")
    
    def _create_fingerprint(self, evt: Dict) -> Tuple:
        """
        foreventcreatefingerprint
        
        fingerprintformat: {COUNTRY}-{YYYYMMDD}-{LOCATION}-{TYPE}-{SEQ}
        example: US-20240115-WDC-PROTEST-001
        """
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
        
        # locationpointshrinkwrite (fetchbefore3charactermotherbigwrite)
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
        
        # orderNo. (baseatGIDmostafter3position)
        seq = str(gid)[-3:].zfill(3)
        
        fingerprint = f"{country}-{date_str}-{location_code}-{event_type}-{seq}"
        
        # generatecanreadmarktopic
        headline = self._generate_headline(actor1, actor2, event_root, location)
        
        # generatedigest
        summary = self._generate_summary(actor1, actor2, location, goldstein, articles)
        
        # closekeyparticipant
        key_actors = json.dumps([a for a in [actor1, actor2] if a and a not in ['some country', 'objectmethod']])
        
        # eventtypetag
        event_label = self._get_event_label(event_root)
        
        # seriousscheduleevaluatedivide (1-10)
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
    
    async def _update_region_stats(self, date: str):
        """update region statistics"""
        logger.info(f"🌍 update region statistics: {date}")
        
        # bycountrystatistics
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
        """, (date,))
        
        # batchinsert
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
                    r['region'], r['region_name'][:100], date, 
                    r['event_count'], r['conflict_intensity'], 
                    r['cooperation_intensity'], r['avg_tone'], actors
                ))
                updated += 1
            except Exception as e:
                logger.warning(f"    skiplocationarea {r['region']}: {e}")
        
        logger.info(f"  ✓ update {updated} locationarea")
    
    async def _update_geo_grid(self, date: str):
        """update geo gridhot"""
        logger.info(f"🗺️ update geo grid: {date}")
        
        # by0.5schedulegridaggregate
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
        """, (date,))
        
        # batchinsert
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
                    grid_id, g['lat_grid'], g['lng_grid'], date,
                    g['event_count'], g['conflict_sum'], 
                    g['avg_goldstein'], g['avg_tone']
                ))
                updated += 1
            except Exception as e:
                logger.warning(f"    skipgrid {grid_id}: {e}")
        
        logger.info(f"  ✓ update {updated} grid")
    
    async def _identify_hot_events(self, date: str):
        """recognizeandupdatehoteventfingerprintreference"""
        logger.info(f"🔥 identify hot events: {date}")
        
        # fetchwhenbeforehoteventGID
        result = await self.pool.fetchone("""
            SELECT hot_event_fingerprints 
            FROM daily_summary 
            WHERE date = %s
        """, (date,))
        
        if not result or not result['hot_event_fingerprints']:
            logger.info("  ⚠️ nohoteventdata")
            return
        
        hot_fingerprints_data = result['hot_event_fingerprints']
        if isinstance(hot_fingerprints_data, str):
            gids = json.loads(hot_fingerprints_data)
        else:
            gids = hot_fingerprints_data
        
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
            """, (json.dumps(fingerprints), date))
            
            logger.info(f"  ✓ update {len(fingerprints)} hoteventfingerprint")


async def main():
    """maininputmouth"""
    # parsearguments
    target_date = None
    if len(sys.argv) > 1:
        target_date = sys.argv[1]
        # validatedateformat
        try:
            datetime.strptime(target_date, '%Y-%m-%d')
        except ValueError:
            print(f"❌ dateformaterror: {target_date}")
            print("   correctconfirmformat: YYYY-MM-DD")
            sys.exit(1)
    
    # runETL
    pipeline = GDELTETLPipeline()
    try:
        await pipeline.initialize()
        await pipeline.run_daily_etl(target_date)
    finally:
        await pipeline.close()


if __name__ == "__main__":
    asyncio.run(main())
