output "vpc_id" { value = aws_vpc.this.id }
output "public_subnet_ids" { value = aws_subnet.public[*].id }
output "application_subnet_ids" { value = aws_subnet.application[*].id }
output "database_subnet_ids" { value = aws_subnet.database[*].id }
output "application_security_group_id" { value = aws_security_group.application.id }
output "nat_gateway_ids" { value = aws_nat_gateway.this[*].id }

