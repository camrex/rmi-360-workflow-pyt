def lambda_handler(event, context):
    """
    Disables a specified AWS CloudWatch Events rule using the provided event payload.
    
    Args:
        event: A dictionary containing the 'rule_name' of the CloudWatch Events rule to disable and optionally the 'region' (defaults to 'us-east-2').
        context: AWS Lambda context object (unused).
    
    Returns:
        A dictionary with an HTTP status code and a message indicating success or failure.
    """
    import boto3
    """
    AWS Lambda function to disable a CloudWatch Events rule.
    
    Args:
        event (dict): Lambda event containing:
            - rule_name (str): Name of the CloudWatch Events rule to disable
            - region (str, optional): AWS region (defaults to "us-east-2")
        context (LambdaContext): Lambda context object
      
    Returns:
        dict: Response with status code and message/error
    """
    rule_name = event.get("rule_name")
    region = event.get("region", "us-east-2")

    if not rule_name:
        return {"statusCode": 400, "error": "Missing rule_name in event payload."}

    try:
        client = boto3.client("events", region_name=region)
        client.disable_rule(Name=rule_name)
        return {
            "statusCode": 200,
            "message": f"CloudWatch rule '{rule_name}' disabled successfully."
        }
    except Exception as e:
        print(f"Error disabling rule '{rule_name}': {str(e)}")
        return {
            "statusCode": 500,
            "error": str(e)
        }
