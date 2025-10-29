# 🚀 RMI 360° EC2 Processing Environment — Full Setup Guide

## 🔹 Step 0: Confirm prerequisites
- AWS region: **`us-east-2`**
- Buckets created:
  - **rmi-360-raw** → private (raw reels)
  - **rmi-360-prod** → public read (final processed images)
- ArcGIS Pro & MistikaVR installers ready
- vCPU quota request for **G / G6 family** approved (e.g., 32 vCPUs)

## 🔹 Step 1: Bucket configuration

### 🪣 rmi-360-raw (private)
**Settings:**
- **Versioning:** Enabled  
- **Default encryption:** SSE-S3 (AES-256)  
- **Block public access:** All ON  
- **Bucket policy:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowUploaders",
      "Effect": "Allow",
      "Principal": {
        "AWS": [
          "arn:aws:iam::<account_id>:role/rmi-ec2-processing-role",
          "arn:aws:iam::<account_id>:user/<username>"
        ]
      },
      "Action": [
        "s3:ListBucket",
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::rmi-360-raw",
        "arn:aws:s3:::rmi-360-raw/*"
      ]
    }
  ]
}
```
- **Tags:**
  | Key | Value |
  |------|--------|
  | Owner | <username> |
  | Department | RMI Valuation |
  | Environment | production |
  | Purpose | rmi-360-processing |

### 🪣 rmi-360-prod (public read)
**Settings:**
- **Versioning:** Disabled  
- **Default encryption:** SSE-S3 (AES-256)  
- **Block public access:** Partially OFF (allow public bucket policies)  
- **Bucket policy:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "PublicRead",
      "Effect": "Allow",
      "Principal": "*",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::rmi-360-prod/*"
    },
    {
      "Sid": "AllowUploaderWrites",
      "Effect": "Allow",
      "Principal": {
        "AWS": [
          "arn:aws:iam::<account_id>:role/rmi-ec2-processing-role",
          "arn:aws:iam::<account_id>:user/<username>"
        ]
      },
      "Action": [
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::rmi-360-prod/*"
    }
  ]
}
```
- **Tags:** same as above

## 🔹 Step 2: IAM setup

### IAM Policy (rmi-ec2-s3-access)
**Description:** Allows EC2 instances to read from `rmi-360-raw` and write to `rmi-360-prod` for 360° processing.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ListRawAndProd",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::rmi-360-raw",
        "arn:aws:s3:::rmi-360-prod"
      ]
    },
    {
      "Sid": "ReadRawObjects",
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::rmi-360-raw/*"
    },
    {
      "Sid": "WriteProdObjects",
      "Effect": "Allow",
      "Action": ["s3:PutObject","s3:DeleteObject"],
      "Resource": "arn:aws:s3:::rmi-360-prod/*"
    }
  ]
}
```

### IAM Role: rmi-ec2-processing-role
- Type: EC2
- Attached policy: `rmi-ec2-s3-access`
- Description: EC2 role for ArcGIS Pro + MistikaVR processing; provides S3 access to raw and production buckets.
- Tags: same 4 keys (Owner, Department, Environment, Purpose)

## 🔹 Step 3: Networking setup

### VPC
If no default VPC exists → Create Default VPC in console.

Otherwise, create manually with CIDR `10.0.0.0/16`, subnet `10.0.1.0/24`, IGW + route table for public internet access.

### Security Group: rmi-render-sg
**Description:** Allows RDP (TCP 3389) access from trusted IPs and outbound internet access for ArcGIS Pro + MistikaVR 360° processing.

| Rule Type | Protocol | Port | Source | Purpose |
|------------|-----------|--------|---------|----------|
| RDP | TCP | 3389 | your office/VPN IP (e.g., `203.0.113.15/32`) | remote access |
| All outbound | All | All | 0.0.0.0/0 | allow updates + S3 access |

Tags: same as before.

## 🔹 Step 4: Key pair
- Create `rmi-render-key` (RSA, PEM format)
- Use for decrypting Windows Administrator password.

## 🔹 Step 5: Launch EC2 instance

| Setting | Value |
|----------|--------|
| AMI | Microsoft Windows Server 2022 Base |
| Instance type | g6.2xlarge (preferred) or g5.2xlarge |
| IAM Role | rmi-ec2-processing-role |
| Key pair | rmi-render-key |
| VPC | rmi-360-vpc (or default) |
| Subnet | rmi-360-public-subnet |
| Auto-assign Public IP | Enabled |
| Security Group | rmi-render-sg |
| Storage (root) | 150 GiB gp3 |
| Storage (data) | 2000 GiB gp3 (xvdb), 12000 IOPS, 750 MB/s, Delete on Termination: Yes |

### User Data (auto-setup for D:\rmi)
```powershell
<powershell>
$rawDisks = Get-Disk | Where-Object PartitionStyle -Eq 'RAW'
if (-not $rawDisks) {
  $rawDisks = Get-Disk | Where-Object { $_.Number -ne (Get-Partition -DriveLetter C).DiskNumber }
}
$disk = $rawDisks | Sort-Object Size -Descending | Select-Object -First 1
if ($disk) {
  Initialize-Disk -Number $disk.Number -PartitionStyle GPT -PassThru | Out-Null
  $part = New-Partition -DiskNumber $disk.Number -UseMaximumSize -DriveLetter 'D'
  Format-Volume -Partition $part -FileSystem NTFS -NewFileSystemLabel 'SCRATCH' -Confirm:$false
}
New-Item -ItemType Directory -Force -Path 'D:\rmi\scratch','D:\rmi\out','D:\rmi\logs' | Out-Null
[System.Environment]::SetEnvironmentVariable('RMI_LOCAL_ROOT','D:\rmi','Machine')
</powershell>
```

## 🔹 Step 6: First login & software setup

1. RDP into instance (use decrypted password from key pair).  
2. Install NVIDIA Data Center driver (L4 or A10G, depending on instance).  
3. Install ArcGIS Pro and sign in.  
4. Install MistikaVR (include CLI components).  
5. Clone repo:
```powershell
git clone https://github.com/camrex/rmi-360-workflow-pyt.git D:\rmi\rmi-360-workflow-pyt
```
6. Create/update config.yaml:
```yaml
runtime:
  local_root: "D:/rmi"
aws:
  region: us-east-2
  s3_bucket: rmi-360-prod
  s3_bucket_raw: rmi-360-raw
  auth_mode: instance
  use_acceleration: false
  max_workers: "cpu*8"
```

## 🔹 Step 7: Tags
Apply to all resources (buckets, roles, instance, SG, volumes, AMI):

| Key | Value |
|------|--------|
| Owner | camrex |
| Department | RMI Valuation |
| Environment | production |
| Purpose | rmi-360-processing |

## 🔹 Step 8: Smoke test
1. Upload a single reel to `s3://rmi-360-raw/proj425/reels/reel_0001/...`
2. Launch ArcGIS Pro → run toolbox
   - Stage from S3: ✅
   - Prefix: `proj425/reels/reel_0001/...`
   - Project folder: `D:\rmi\proj425`
3. Verify:
   - Files staged to `D:\rmi\scratch\proj425`
   - Output uploaded to `rmi-360-prod` (publicly accessible)

## 🔹 Step 9: Bake AMI
When verified:
- Stop instance → **Actions → Image → Create image**
- Name: `rmi-renderbox-win2022-g6-v1`
- Description: GPU-enabled Windows Server 2022 AMI for ArcGIS Pro + MistikaVR 360° processing.

## 🔹 Step 10: Routine workflow
For each new capture:
1. Launch from AMI → pick size (g6.2xlarge)  
2. Attach 2 TB gp3 volume (Delete on Termination: Yes)  
3. Run workflow → verify S3 output → terminate instance.

---
**End of Guide**
