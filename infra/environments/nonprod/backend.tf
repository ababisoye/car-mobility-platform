terraform {
  backend "s3" {
    key          = "luxury-rental/nonprod/foundation.tfstate"
    use_lockfile = true
    encrypt      = true
  }
}

