# Oracle Cloud Infrastructure (OCI) Deployment Configuration
# for Angavu Intelligence Training Loop
#
# This configuration deploys the federated learning aggregation server
# and training loop orchestrator on Oracle Cloud Infrastructure.
#
# Prerequisites:
#   - OCI CLI configured (oci setup)
#   - Terraform >= 1.5
#   - Docker for building container images
#
# Architecture:
#   - Compute: OCI Ampere A1 (ARM) for cost-efficient training
#   - Storage: OCI Object Storage for model checkpoints
#   - Database: OCI Autonomous DB for training state
#   - Networking: OCI Load Balancer for FL aggregation endpoint

# ─────────────────────────────────────────────────────────────────────
# Provider Configuration
# ─────────────────────────────────────────────────────────────────────

terraform {
  required_version = ">= 1.5"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 5.0"
    }
  }
}

variable "tenancy_ocid" {
  description = "OCI Tenancy OCID"
  type        = string
}

variable "compartment_ocid" {
  description = "OCI Compartment OCID for training infrastructure"
  type        = string
}

variable "region" {
  description = "OCI Region (e.g., af-johannesburg-1 for Africa)"
  type        = string
  default     = "af-johannesburg-1"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "production"
}

# ─────────────────────────────────────────────────────────────────────
# Networking
# ─────────────────────────────────────────────────────────────────────

resource "oci_core_vcn" "training_vcn" {
  compartment_id = var.compartment_ocid
  cidr_block     = "10.0.0.0/16"
  display_name   = "angavu-training-vcn"
  dns_label      = "angavutraining"
}

resource "oci_core_subnet" "training_subnet" {
  compartment_id = var.compartment_ocid
  vcn_id         = oci_core_vcn.training_vcn.id
  cidr_block     = "10.0.1.0/24"
  display_name   = "training-subnet"
  dns_label      = "training"
}

# ─────────────────────────────────────────────────────────────────────
# Compute — Training Loop Orchestrator (ARM-based Ampere A1)
# ─────────────────────────────────────────────────────────────────────

resource "oci_core_instance" "training_orchestrator" {
  compartment_id      = var.compartment_ocid
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  display_name        = "angavu-training-orchestrator"
  shape               = "VM.Standard.A1.Flex"

  shape_config {
    ocpus       = 4
    memory_in_gbs = 24
  }

  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.ubuntu_arm.images[0].id
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.training_subnet.id
    assign_public_ip = true
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data = base64encode(templatefile("${path.module}/cloud-init.yaml", {
      environment = var.environment
    }))
  }
}

# ─────────────────────────────────────────────────────────────────────
# Compute — FL Aggregation Server (GPU for model validation)
# ─────────────────────────────────────────────────────────────────────

resource "oci_core_instance" "fl_aggregation_server" {
  compartment_id      = var.compartment_ocid
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  display_name        = "angavu-fl-aggregation"
  shape               = "VM.Standard.A1.Flex"

  shape_config {
    ocpus       = 8
    memory_in_gbs = 48
  }

  source_details {
    source_type = "image"
    source_id   = data.oci_core_images.ubuntu_arm.images[0].id
  }

  create_vnic_details {
    subnet_id        = oci_core_subnet.training_subnet.id
    assign_public_ip = true
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data = base64encode(templatefile("${path.module}/cloud-init-fl.yaml", {
      environment = var.environment
    }))
  }
}

# ─────────────────────────────────────────────────────────────────────
# Object Storage — Model Checkpoints
# ─────────────────────────────────────────────────────────────────────

resource "oci_objectstorage_bucket" "model_checkpoints" {
  compartment_id = var.compartment_ocid
  name           = "angavu-model-checkpoints"
  namespace      = data.oci_objectstorage_namespace.ns.namespace
  access_type    = "NoPublic"
  versioning     = "Enabled"

  freeform_tags = {
    "project"     = "angavu-intelligence"
    "environment" = var.environment
    "purpose"     = "model-checkpoints"
  }
}

resource "oci_objectstorage_bucket" "training_logs" {
  compartment_id = var.compartment_ocid
  name           = "angavu-training-logs"
  namespace      = data.oci_objectstorage_namespace.ns.namespace
  access_type    = "NoPublic"

  freeform_tags = {
    "project"     = "angavu-intelligence"
    "environment" = var.environment
    "purpose"     = "training-logs"
  }
}

# ─────────────────────────────────────────────────────────────────────
# Autonomous Database — Training State & Metrics
# ─────────────────────────────────────────────────────────────────────

resource "oci_database_autonomous_database" "training_db" {
  compartment_id = var.compartment_ocid
  db_name        = "angavutraining"
  display_name   = "angavu-training-db"
  admin_password = var.db_admin_password

  cpu_core_count       = 2
  data_storage_size_in_tbs = 1
  db_workload          = "OLTP"
  is_auto_scaling_enabled = true
  is_free_tier         = false

  freeform_tags = {
    "project"     = "angavu-intelligence"
    "environment" = var.environment
  }
}

# ─────────────────────────────────────────────────────────────────────
# Load Balancer — FL Aggregation Endpoint
# ─────────────────────────────────────────────────────────────────────

resource "oci_load_balancer_load_balancer" "fl_endpoint" {
  compartment_id = var.compartment_ocid
  display_name   = "angavu-fl-endpoint"
  shape          = "flexible"
  subnet_ids     = [oci_core_subnet.training_subnet.id]

  shape_details {
    minimum_bandwidth_in_mbps = 10
    maximum_bandwidth_in_mbps = 100
  }
}

resource "oci_load_balancer_backend_set" "fl_backend" {
  load_balancer_id = oci_load_balancer_load_balancer.fl_endpoint.id
  name             = "fl-aggregation-backends"
  policy           = "ROUND_ROBIN"

  health_checker {
    protocol = "HTTP"
    port     = 8000
    url_path = "/health"
  }
}

# ─────────────────────────────────────────────────────────────────────
# Data Sources
# ─────────────────────────────────────────────────────────────────────

data "oci_identity_availability_domains" "ads" {
  compartment_id = var.tenancy_ocid
}

data "oci_core_images" "ubuntu_arm" {
  compartment_id   = var.compartment_ocid
  operating_system = "Canonical Ubuntu"
  shape            = "VM.Standard.A1.Flex"
  sort_by          = "TIMECREATED"
  sort_order       = "DESC"
}

data "oci_objectstorage_namespace" "ns" {
  compartment_id = var.compartment_ocid
}

# ─────────────────────────────────────────────────────────────────────
# Outputs
# ─────────────────────────────────────────────────────────────────────

output "orchestrator_ip" {
  value = oci_core_instance.training_orchestrator.public_ip
}

output "fl_server_ip" {
  value = oci_core_instance.fl_aggregation_server.public_ip
}

output "fl_endpoint_url" {
  value = "https://${oci_load_balancer_load_balancer.fl_endpoint.ip_address_details[0].ip_address}"
}

output "model_bucket" {
  value = oci_objectstorage_bucket.model_checkpoints.name
}

output "training_db_connection" {
  value     = oci_database_autonomous_database.training_db.connection_urls
  sensitive = true
}
