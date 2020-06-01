from __future__ import print_function

import json
import os
import sys
import time

import boto3

sys.path.append('/opt/pooled-cell-painting-lambda')

import create_CSVs
import run_DCP
import create_batch_jobs
import helpful_functions

s3 = boto3.client('s3')
sqs = boto3.client('sqs')
pipeline_name = '2_Apply_Illum_forCP_TI2.cppipe'
metadata_file_name = '/tmp/metadata.json'
fleet_file_name = 'illumFleet.json'
prev_step_app_name = '2018_11_20_Periscope_X_IllumPainting'

def lambda_handler(event, context):
    # Log the received event
    bucket_name = event['Records'][0]['s3']['bucket']['name']
    key = event['Records'][0]['s3']['object']['key']
    keys = [x['s3']['object']['key'] for x in event['Records'] ]
    plate = key.split('/')[-2]
    batch = key.split('/')[-4]
    image_prefix = key.split(batch)[0]
    prefix = os.path.join(image_prefix,'workspace/')
    
    #get the metadata file, so we can add stuff to it
    metadata_on_bucket_name = os.path.join(prefix,'metadata',batch,'metadata.json')
    metadata = helpful_functions.download_and_read_metadata_file(s3, bucket_name, metadata_file_name, metadata_on_bucket_name)
    
    image_dict = metadata ['painting_file_data']
    num_series = int(metadata['painting_rows']) * int(metadata['painting_columns'])
    
    #Pull the file names we care about, and make the CSV
    platelist = image_dict.keys()
    

    plate = key.split('/')[-2]
    platedict = image_dict[plate]
    well_list = platedict.keys()
    paint_cycle_name = platedict[well_list[0]].keys()[0]
    per_well_im_list = []
    for eachwell in well_list:
        per_well = platedict[eachwell][paint_cycle_name]
        if len(per_well)==3: #only keep full wells
            per_well_im_list.append(per_well)
    bucket_folder = '/home/ubuntu/bucket/'+image_prefix+batch+'/images/'+plate+'/'+paint_cycle_name
    illum_folder =  '/home/ubuntu/bucket/'+image_prefix+batch+'/illum/'+plate
    per_plate_csv = create_CSVs.create_CSV_pipeline2(plate, num_series, bucket_folder, illum_folder, per_well_im_list, well_list)
    csv_on_bucket_name = prefix + 'load_data_csv/'+batch+'/'+plate+'/load_data_pipeline2.csv'
    print(csv_on_bucket_name)
    with open(per_plate_csv,'rb') as a:
        s3.put_object(Body= a, Bucket = bucket_name, Key = csv_on_bucket_name )
        
    #Now let's check if it seems like the whole thing is done or not
    sqs = boto3.client('sqs')
    
    filter_prefix = image_prefix+batch+'/illum'
    expected_len = (int(metadata['painting_channels'])+1)*len(platelist)
    
    done = helpful_functions.check_if_run_done(s3, bucket_name, filter_prefix, expected_len, prev_step_app_name, sqs)
    
    if not done:
        print('Still work ongoing')
    
    else:
        # first let's just try to run the monitor on 
        APP_NAME = prev_step_app_name
        print('Trying monitor')
        try:
            import botocore
            helpful_functions.try_to_run_monitor(s3, bucket_name, prefix, batch, '1', prev_step_app_name)
        except botocore.exceptions.ClientError as error:
            print('Monitor cleanup of previous step failed with error: ',error)
            print('Usually this is no existing queue by that name, maybe a previous monitor cleaned up')
        except:
            print('Monitor cleanup of previous step failed with error',sys.exc_info()[0])
            pass
        
        #now let's do our stuff!
        run_DCP.run_setup(bucket_name,prefix,batch,'2')
        
        #make the jobs
        create_batch_jobs.create_batch_jobs_2(image_prefix,batch,pipeline_name,platelist, well_list)
        
        #Start a cluster
        run_DCP.run_cluster(bucket_name,prefix,batch,'2', fleet_file_name, len(platelist)*len(well_list))  

        #Run the monitor
        run_DCP.run_monitor(bucket_name, prefix, batch,'2')
        print('Go run the monitor now')
    

    