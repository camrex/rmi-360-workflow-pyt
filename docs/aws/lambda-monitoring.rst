Lambda Monitoring
=================

.. warning::

   **The AWS side of the upload monitor was removed on 2026-10-16** (rmi-aws-infra change record
   0017). Gone from account 987980910568, us-east-2: the Lambdas ``UploadProgressMonitor`` and
   ``DisableUploadMonitorRule``, the EventBridge rule ``UploadProgressScheduleRule``, the role
   ``LambdaProgressMonitorRole`` and its policy ``LambdaUploadMonitorAccess``. The monitor had not
   run since 2025-05-22, and its permissions only reached ``rmi-orient-img``, which was also deleted
   (change record 0012).

   **Run Copy To AWS with "Deploy Upload Monitor?" unticked.** The tool defaults to ticked. With the
   Lambdas gone it tries to recreate them using ``aws.lambda_role_arn``, and if that fails it
   raises before the upload starts. Using the monitor again needs a new IAM role (and a change
   record in rmi-aws-infra) plus permissions for the current bucket, ``rmi-360-prod``.

*This section is under development. Content will be migrated from the legacy documentation.*

Lambda-based upload monitoring and status tracking including:

- Lambda function setup
- Progress monitoring
- Status dashboard
- Scheduling and automation

For now, see the legacy documentation in ``docs_legacy/`` for Lambda monitoring details.
