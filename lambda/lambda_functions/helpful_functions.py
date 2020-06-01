import json

import run_DCP

def parse_image_names(imlist,filter):
    image_dict = {}
    for image in imlist:
        if '.nd2' in image:
            if filter in image:
                prePlate,platePlus = image.split('images/')
                plate,cycle,imname = platePlus.split('/')
                well = imname[:imname.index('_')]
                if plate not in image_dict.keys():
                    image_dict[plate] = {well:{cycle:[imname]}}
                else:
                    if well not in image_dict[plate].keys():
                        image_dict[plate][well] = {cycle:[imname]}
                    else:
                        if cycle not in image_dict[plate][well].keys():
                            image_dict[plate][well][cycle] = [imname]
                        else:
                            image_dict[plate][well][cycle] += [imname]
    return image_dict
    
def download_and_read_metadata_file(s3, bucket_name, metadata_file_name, metadata_on_bucket_name):
    with open(metadata_file_name, 'wb') as f:
        s3.download_fileobj(bucket_name,  metadata_on_bucket_name, f)
    with open(metadata_file_name, 'r') as input_metadata:
        metadata = json.load(input_metadata)
    return metadata    
        
def write_metadata_file(s3, bucket_name, metadata, metadata_file_name, metadata_on_bucket_name):
    with open(metadata_file_name, 'wb') as f:
        json.dump(metadata, f)
    with open(metadata_file_name, 'r') as metadata:
        s3.put_object(Body = metadata, Bucket = bucket_name, Key = metadata_on_bucket_name)
        
def paginate_a_folder(s3,bucket_name,prefix):
    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
    image_list = []
    #image_list = s3.list_objects_v2(Bucket=bucket_name,Prefix=)['Contents']
    for page in pages:
        image_list += [x['Key'] for x in page['Contents']]
    return image_list

def check_if_run_done(s3, bucket_name, filter_prefix, expected_len, prev_step_app_name, sqs):
    #Step 1- how many files are there in the illum folder?
    image_list = paginate_a_folder(s3, bucket_name, filter_prefix)
    if len(image_list) >= expected_len:
        return True
    else:
        print('Only ',len(image_list),' output files so far')
    
    #Maybe something died, but everything is done, and you have a monitor on that already cleaned up your queue
    queue_url = check_named_queue(sqs, prev_step_app_name+'Queue')
    if queue_url == None:
        return True
        
    #Maybe something died, and now your queue is just at 0 jobs
    attributes = sqs.get_queue_attributes(QueueUrl=queue_url,AttributeNames=['ApproximateNumberOfMessages','ApproximateNumberOfMessagesNotVisible'])
    if attributes['Attributes']['ApproximateNumberOfMessages'] + attributes['Attributes']['ApproximateNumberOfMessagesNotVisible'] == 0:
        return True
        
    #or, we're just not done yet
    return False

def check_named_queue(sqs, SQS_QUEUE_NAME):
    result = sqs.list_queues()
    if 'QueueUrls' in result.keys():
        for u in result['QueueUrls']:
            if u.split('/')[-1] == SQS_QUEUE_NAME:
                return u
    return None
    
def try_to_run_monitor(s3, bucket_name, prefix, batch, step, prev_step_app_name):
    prev_step_monitor_bucket_name = prefix + 'monitors/'+batch+'/'+step+'/'+prev_step_app_name + 'SpotFleetRequestId.json'
    prev_step_monitor_name = '/tmp/'+prev_step_app_name + 'SpotFleetRequestId.json'
    with open(prev_step_monitor_name, 'wb') as f:
        s3.download_fileobj(bucket_name,  prev_step_monitor_bucket_name, f)
    run_DCP.grab_batch_config(bucket_name,prefix,batch,step)
    import boto3_setup
    boto3_setup.monitor()