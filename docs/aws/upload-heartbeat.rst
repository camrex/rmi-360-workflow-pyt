Upload Heartbeat
================

*Copy To AWS* (and step 17 of *Process 360 Workflow*) reports its progress as a small
JSON document, the **upload heartbeat**:

- ``s3://<aws.s3_bucket_raw>/status/<project.slug>/upload_progress.json``. For RMI
  that is ``s3://rmi-360-raw/status/RMI…/upload_progress.json``.
- A local copy, ``aws_upload_status.json``, sits next to the upload log.

It is rewritten about once a minute while the upload runs, and once more when it ends.
It replaces the retired Lambda upload monitor: nothing runs in AWS, and no Lambda,
EventBridge or IAM is involved. Any alerting on top of it belongs to rmi-aws-infra.

What it contains
----------------

.. code-block:: json

   {
     "phase": "uploading",
     "started_at": 1792345678.1,
     "last_update": 1792345912.4,
     "completed_at": null,
     "totals": {"files": 1200, "uploaded": 340, "skipped": 12, "failed": 0,
                "bytes_uploaded": 6012345678},
     "groups": {"panoramas": {"planned_files": 1200, "uploaded": 340, "...": "..."}},
     "meta": {"project": "RMI26150", "bucket": "rmi-360-prod", "prefix": "RMI26150",
              "skipped_from_log": 0, "tool": "copy_to_aws"}
   }

``phase`` ends as ``complete``, ``cancelled`` (cancel trigger) or ``error`` (nothing
uploaded and something failed). Times are Unix seconds. A heartbeat whose
``last_update`` is more than a few minutes old while ``phase`` is not final means the
upload stopped (machine asleep, Pro closed, sign-in expired).

How it is written
-----------------

- With the same named AWS profile as the upload (see :doc:`setup-guide`), which may put
  under ``rmi-360-raw/status/RMI*/``. Every put is SSE-S3 encrypted, since the bucket
  refuses unencrypted puts.
- ``rmi-360-raw`` is versioned. A lifecycle rule (rmi-aws-infra change 0049) expires
  old heartbeat versions under ``status/`` after a day.
- A background thread publishes it on a timer, outside the upload threads, so
  heartbeats keep coming during long transfers and a slow S3 call can't hold up an
  upload. The client has short timeouts. A failed heartbeat never stops the upload:
  the tool logs one warning at the end. The thread always stops when the upload
  ends, including when it fails with an error (phase ``error``).
- No setting turns it on. If ``aws.s3_bucket_raw`` or ``project.slug`` is empty, the
  tool says so and uploads without a heartbeat.

Reading it
----------

.. code-block:: bash

   aws s3 cp s3://rmi-360-raw/status/RMI26150/upload_progress.json - --profile rmi-360-workflow-pyt
