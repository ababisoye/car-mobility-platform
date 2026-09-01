terraform {
  backend "s3" {
    key          = "luxury-rental/production/foundation.tfstate"
    use_lockfile = true
    encrypt      = true
  }
}

