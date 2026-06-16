variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "ap-southeast-2"
}

variable "project_name" {
  description = "Project name used as prefix for all resources"
  type        = string
  default     = "documind"
}

variable "openai_api_key" {
  description = "OpenAI API key — passed as Lambda env var"
  type        = string
  sensitive   = true
}

variable "database_url" {
  description = "PostgreSQL connection string for Lambda"
  type        = string
  sensitive   = true
}

variable "ecr_image_uri" {
  description = "ECR image URI for the Lambda container (e.g. 123456789.dkr.ecr.ap-southeast-2.amazonaws.com/documind:latest)"
  type        = string
}
