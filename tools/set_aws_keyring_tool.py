import arcpy
import keyring
from utils.config_loader import load_config
from utils.arcpy_utils import log_message


class SetAWSKeyringCredentialsTool(object):
    def __init__(self):
        self.label = "Set AWS Keyring Credentials"
        self.description = "Store AWS credentials securely in the system keyring for use by the Copy to AWS tool."
        self.category = "Setup"

    def getParameterInfo(self):
        return [
            arcpy.Parameter(
                displayName="AWS Access Key ID",
                name="access_key_id",
                datatype="GPString",
                parameterType="Required",
                direction="Input"
            ),
            arcpy.Parameter(
                displayName="AWS Secret Access Key",
                name="secret_access_key",
                datatype="GPString",
                parameterType="Required",
                direction="Input"
            )
        ]

    def execute(self, parameters, messages):
        """
        Stores AWS credentials in the system keyring for secure access by AWS-related tools.
        
        Extracts the AWS Access Key ID and Secret Access Key from input parameters and saves them
        to the system keyring under a configurable service name. Logs success or error messages
        using the provided messaging object.
        """
        try:
            config = load_config()
            service_name = config.get("copy_to_aws", {}).get("keychain_service_name", "rmi_s3")
            access_key_id = parameters[0].valueAsText
            secret_access_key = parameters[1].valueAsText

            if not (access_key_id and secret_access_key):
                log_message("All parameters are required.", messages, level="error", error_type=ValueError)

            keyring.set_password(service_name, "aws_access_key_id", access_key_id)
            keyring.set_password(service_name, "aws_secret_access_key", secret_access_key)

            log_message(f"✅ AWS credentials saved to keyring under service '{service_name}'.", messages)

        except Exception as e:
            log_message(f"❌ Failed to set AWS credentials: {e}", messages, level="error", error_type=RuntimeError)
