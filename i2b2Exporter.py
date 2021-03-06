#!env python
#
#  Program to extract a query from I2b2 and generate a sqllite file output of the data
#  See : https://www.i2b2.org/software/files/PDF/current/CRC_Plugin_Analysis.pdf
#
#  by George Kowalski of the Medical College of Wisconsin CTSI

#

import cx_Oracle
import json
import sys
import os, os.path
import dbconnection as db
import logging
import sqlite3 as sqllite

# Logging set up
FORMAT = '%(asctime)-15s  %(message)s'
logging.basicConfig(format=FORMAT)
d = { }
logger = logging.getLogger('i2b2Exporter')
logger.warning('Program Started: %s', 'started', extra=d)

# Read in Arguments
# Verify correct argument count

queryName = sys.argv[1]
sqlliteFileName = sys.argv[2]


print ( "We're looking for query  " + queryName )

print ( "We're going to create output sqllite3 database called:  " + sqlliteFileName )

# Load db connection params
db.load_config()

# verify that the query can be found and has only one result
cur = db.get_connection()
cur = db.get_connection().cursor()
cur.execute("select  QUERY_MASTER_ID from   QT_QUERY_MASTER where name = :queryName" , queryName= queryName    )

qtQueryMasterId = cur.fetchone()[0]
if ( cur.rowcount < 1) :
    logger.error("Could not find query in the database : " + queryName)
    sys.exit(1)

if ( cur.rowcount > 1) :
    logger.error("Found more than one query with this name , please make unique : " + queryName)
    sys.exit(1)

logger.warning(cur.rowcount )
logger.warning ( "QT_QUERY_MASTER_ID to process : %s " % qtQueryMasterId )

# Verify we have a patient set to use , else the user just did a query for
# the number of patients.
cur.execute("select  QUERY_INSTANCE_ID from   QT_QUERY_INSTANCE where query_master_id = :qtQueryMasterId" , qtQueryMasterId= qtQueryMasterId    )
qtQueryInstanceId = cur.fetchone()[0]
logger.warning ( "QT_QUERY_INSTANCE_ID to process : %s " % qtQueryInstanceId )

# Get query Result
cur.execute("select  RESULT_INSTANCE_ID from   QT_QUERY_RESULT_INSTANCE where QUERY_INSTANCE_ID = :qtQueryInstanceId and result_type_id = 1 " , qtQueryInstanceId= qtQueryInstanceId    )
qtresultInstanceId = cur.fetchone()[0]
logger.warning ( "QT_RESULT_INSTANCE_ID to process : %s " % qtresultInstanceId  )


# now get patinet Numbers returned
cur.execute("select  DISTINCT( PATIENT_NUM  ) from   QT_PATIENT_SET_COLLECTION WHERE RESULT_INSTANCE_ID = :qtresultInstanceId" , qtresultInstanceId= qtresultInstanceId    )
results = cur.fetchall()
if ( cur.rowcount < 1):
    logger.error("No Patient Numbers found for query , are you sure this is a PatientSet query : %i  "  %  qtresultInstanceId)
    sys.exit(1)

patNumArray = []
for row in results:
    logger.warning("Found PATIENT_NUM %d " , row[0])
    patNumArray.append(row[0])

# process patient set  outputting to sqllite file

# Create sqllite file , deleting old one if found
# initialize it with standard schema from i2b2
if ( os.path.isfile(sqlliteFileName)) :
    logger.warning("Removing existing database file : " + sqlliteFileName)
    #  Add confirmation here
    os.remove (sqlliteFileName)
sqlLiteCon = sqllite.connect(sqlliteFileName);
#  The need for Speed
sqlLiteCon.execute("PRAGMA synchronous=OFF")
sqlLiteCon.execute("PRAGMA journal_mode=OFF")

logger.warning('Creating sqlite schema  ...')
db.executeScriptsFromFile("sql/defaultI2b2Schema.sql", sqlLiteCon)


sqlLiteCon.isolation_level = None


# load patient data
logger.warning("Saving existing Patient Records  ... "  )
sqlLiteCon.execute("begin;")
for patNum in patNumArray  :
    cur.execute("select  * from patient_dimension where  PATIENT_NUM = :patNum" , patNum= patNum    )
    results = cur.fetchall()
    for row in results:
        sqlInsert = """
            INSERT INTO patient_dimension (
                patient_num,
                vital_status_cd,
                birth_date,
                death_date,
                sex_cd,
                age_in_years_num,
                language_cd,
                race_cd,
                marital_status_cd,
                religion_cd,
                zip_cd,
                statecityzip_path,
                income_cd,
                patient_blob,
                update_date,
                download_date,
                import_date,
                sourcesystem_cd,
                upload_id
            ) VALUES (
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
               ?
            )  """

        sqlLiteCon.execute(sqlInsert,  row )

sqlLiteCon.execute("commit;")


# load Visit Dimension data
logger.warning("Saving existing Visit Records  ... "  )

cur.execute("""select * from visit_dimension where patient_num in (
select  DISTINCT( PATIENT_NUM  ) from   QT_PATIENT_SET_COLLECTION WHERE RESULT_INSTANCE_ID = :qtresultInstanceId
) """, qtresultInstanceId = qtresultInstanceId )

results = cur.fetchall()
sqlLiteCon.execute("begin;")

for row in results:
    sqlInsert = """
                  INSERT
        INTO
            visit_dimension
            (
                encounter_num,
                patient_num,
                active_status_cd,
                start_date,
                end_date,
                inout_cd,
                location_cd,
                location_path,
                length_of_stay,
                visit_blob,
                update_date,
                download_date,
                import_date,
                sourcesystem_cd,
                upload_id
            )
            VALUES
            (
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?
            )
              """

    sqlLiteCon.execute(sqlInsert,  row )

sqlLiteCon.execute("commit;")

# Load Concept_dimension
logger.warning("Saving existing Concepts Records  ... "  )

cur.execute("""
  select * from  CONCEPT_DIMENSION where concept_cd in (
        select  distinct ( concept_cd )   from observation_fact where patient_num in (
                select  DISTINCT( PATIENT_NUM  ) from   QT_PATIENT_SET_COLLECTION WHERE RESULT_INSTANCE_ID = :qtresultInstanceId
        )
) order by concept_cd
  """, qtresultInstanceId = qtresultInstanceId )

results = cur.fetchall()

sqlLiteCon.execute("begin;")

for row in results:
    sqlInsert = """
             INSERT
        INTO
            concept_dimension
            (
                concept_path,
                concept_cd,
                name_char,
                concept_blob,
                update_date,
                download_date,
                import_date,
                sourcesystem_cd,
                upload_id
            )
            VALUES
            (
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?,
                ?
            )
                """

    sqlLiteCon.execute(sqlInsert,  row )

sqlLiteCon.execute("commit;")




# load observation fact data

logger.warning("Saving existing Observation Fact Records  ... "  )

cur.execute("""select * from observation_fact where patient_num in (
        select  DISTINCT( PATIENT_NUM  ) from   QT_PATIENT_SET_COLLECTION WHERE RESULT_INSTANCE_ID = :qtresultInstanceId
)  """, qtresultInstanceId = qtresultInstanceId )

results = cur.fetchall()
sqlLiteCon.execute("begin;")
for row in results:
    sqlInsert = """
               INSERT INTO
    observation_fact
    (
        encounter_num,
        patient_num,
        concept_cd,
        provider_id,
        start_date,
        modifier_cd,
        instance_num,
        valtype_cd,
        tval_char,
        nval_num,
        valueflag_cd,
        quantity_num,
        units_cd,
        end_date,
        location_cd,
        observation_blob,
        confidence_num,
        update_date,
        download_date,
        import_date,
        sourcesystem_cd,
        upload_id
    )
    VALUES
    (
        ?,
        ?,
        ?,
        ?,
        ?,
        ?,
        ?,
        ?,
        ?,
        ?,
        ?,
        ?,
        ?,
        ?,
        ?,
        ?,
        ?,
        ?,
        ?,
        ?,
        ?,
        ?
    );
                """

    sqlLiteCon.execute(sqlInsert,  row )

sqlLiteCon.execute("commit;")

# Modifier Dimension, just grab them all as we don't know which are important at this time.



logger.warning("Saving existing Modifiers Records  ... "  )

cur.execute("""SELECT md.modifier_path, md.modifier_cd, md.name_char  FROM modifier_dimension md ORDER BY modifier_path  """ )

results = cur.fetchall()
sqlLiteCon.execute("begin;")
for row in results:
    sqlInsert = """  INSERT INTO modifier_dimension (modifier_path, modifier_cd, name_char) VALUES (?, ?, ?)   """
    sqlLiteCon.execute(sqlInsert,  row )

sqlLiteCon.execute("commit;")


# Save Job information in the file

# INSERT INTO job (pset, label, concepts, name) VALUES (?, ?, ?, ?)
# (64969, u'Breast Cancer 20150105 [1-5-2015] [tmcmahon] [PATIENTSET_64969]', '{"keys": [...], "names": [...]}', , u'heron-64969')
# close , we're done adding data
logger.warning("Updating Job table with results ... "  )

sqlLiteCon.execute("""INSERT
INTO
    job
    (
        pset,
        label,
        concepts,
        name
    )
    VALUES
    ( ?, ?, '', '' );""", ( qtQueryMasterId , queryName))

logger.warning('Creating Indexes in the sqlite database ...')
db.executeScriptsFromFile("sql/defaultI2b2Indexes.sql", sqlLiteCon)
sqlLiteCon.close()



