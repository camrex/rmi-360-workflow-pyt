AWS Setup Guide
===============

The toolbox talks to AWS only through a **named AWS profile**, and it never falls back
to the machine's ``default`` profile. It no longer reads keys from ``config.yaml`` or
the OS keyring. The profile itself must be the IAM Identity Center (SSO) profile
below: the toolbox uses whatever credentials a named profile resolves to, so don't
point it at a profile that holds static keys.

For RMI the profile is **``rmi-360-workflow-pyt``**, issued by rmi-aws-infra
(change record 0049).

What the profile can do
-----------------------

.. list-table::
   :header-rows: 1
   :widths: 45 55

   * - Allowed
     - Resource
   * - List
     - ``rmi-360-prod``, ``rmi-360-raw``
   * - Upload panoramas (``.jpg`` / ``.jpeg`` only)
     - ``rmi-360-prod/RMI*/*``
   * - Read (``HeadObject`` before each upload)
     - ``rmi-360-prod/RMI*/*``
   * - Read and upload project data, and the upload heartbeat
     - ``rmi-360-raw/RMI*/*``, ``rmi-360-raw/status/RMI*/*``
   * - Read the Transfer Acceleration setting
     - ``rmi-360-prod``

Everything else is denied: deletes, Lambda, EventBridge, IAM, bucket configuration,
and any other bucket or key pattern. Project slugs must start with ``RMI``. The
session lasts 1 hour and refreshes from the SSO sign-in, which lasts as long as the
Identity Center portal session (8 hours by default).

Set up a machine
----------------

1. **Install the AWS CLI v2** (``aws --version``).
2. **Add the profile** to ``%USERPROFILE%\.aws\config``. rmi-aws-infra supplies the
   start URL and account id:

   .. code-block:: ini

      [profile rmi-360-workflow-pyt]
      sso_session = rmi
      sso_account_id = <account id>
      sso_role_name = rmi-360-workflow-pyt
      region = us-east-2

      [sso-session rmi]
      sso_start_url = <start url>
      sso_region = us-east-2
      sso_registration_scopes = sso:account:access

3. **Name the profile in the project config**:

   .. code-block:: yaml

      aws:
        profile: "rmi-360-workflow-pyt"

   The config editor's RMI profile sets this for new configs. If ``aws.profile`` is
   blank, the toolbox uses the ``AWS_PROFILE`` environment variable instead.
4. **Remove any static key** from the machine. Delete ``[default]`` keys from
   ``%USERPROFILE%\.aws\credentials`` once rmi-aws-infra has retired them. Delete old
   keyring entries (service ``rmi_s3`` / ``aws_s3``): the toolbox no longer reads them.

Before each run
---------------

Sign in from a terminal:

.. code-block:: bash

   aws sso login --profile rmi-360-workflow-pyt

This caches a token under ``%USERPROFILE%\.aws\sso\cache``. ArcGIS Pro's Python reads
the same ``.aws`` folder, so tools run inside Pro use the sign-in without restarting
Pro. Check it with:

.. code-block:: bash

   aws sts get-caller-identity --profile rmi-360-workflow-pyt

Sign in right before a long upload. A run that outlasts the portal session (8 hours by
default) fails part-way. Re-run it: uploaded files are skipped.

How ArcGIS Pro picks up the profile
-----------------------------------

- Toolbox tools read ``aws.profile`` from the project's ``config.yaml``. This is the
  recommended route, since it travels with the project.
- Without it, they use ``AWS_PROFILE``. To set it for Pro, run
  ``setx AWS_PROFILE rmi-360-workflow-pyt`` once, then restart ArcGIS Pro.
- The scripts in ``scripts/`` (``upload_to_s3.py``, ``download_project_files.py``)
  follow the same rules.

If neither is set, or the profile is ``default``, every AWS step stops with an error
naming the setting to fix. A profile that is missing from ``.aws/config`` stops with a
pointer to this page.

Uploads never overwrite
-----------------------

*Copy To AWS* checks each key with ``HeadObject`` before uploading and skips it if it
already exists (``already in S3`` in the upload log). An overwrite in ``rmi-360-prod``
would re-run tiling for that panorama. To replace an image on purpose, ask
rmi-aws-infra.

Transfer Acceleration
---------------------

Transfer Acceleration is enabled on ``rmi-360-prod``, and the uploader uses it when
``aws.use_acceleration`` is true (the default). It adds $0.04/GB to the upload.

See also: :doc:`s3-uploads`.
