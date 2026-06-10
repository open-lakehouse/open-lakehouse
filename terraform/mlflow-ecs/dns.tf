# ============================================================================
# ACM certificate (DNS-validated) for the ALB. Gated on enable_https.
# ============================================================================
resource "aws_acm_certificate" "mlflow" {
  count             = local.enable_https ? 1 : 0
  domain_name       = var.cert_domain_name != "" ? var.cert_domain_name : var.domain_name
  validation_method = "DNS"
  tags              = var.tags

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "cert_validation" {
  for_each = local.enable_https ? {
    for dvo in aws_acm_certificate.mlflow[0].domain_validation_options :
    dvo.domain_name => {
      name   = dvo.resource_record_name
      type   = dvo.resource_record_type
      record = dvo.resource_record_value
    }
  } : {}

  zone_id         = var.hosted_zone_id
  name            = each.value.name
  type            = each.value.type
  records         = [each.value.record]
  ttl             = 60
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "mlflow" {
  count                   = local.enable_https ? 1 : 0
  certificate_arn         = aws_acm_certificate.mlflow[0].arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}

# ============================================================================
# ALB — public tracking server (HTTP, or HTTPS when a domain is configured).
# ============================================================================
resource "aws_lb" "ui" {
  name               = "${var.name_prefix}-ui"
  load_balancer_type = "application"
  internal           = false
  security_groups    = [aws_security_group.alb.id]
  subnets            = local.subnet_ids
  tags               = var.tags
}

resource "aws_lb_target_group" "ui" {
  name        = "${var.name_prefix}-ui"
  port        = var.mlflow_port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = local.vpc_id
  tags        = var.tags

  health_check {
    path                = "/health"
    protocol            = "HTTP"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "ui_http" {
  load_balancer_arn = aws_lb.ui.arn
  port              = 80
  protocol          = "HTTP"

  # With HTTPS enabled, port 80 just 301-redirects to 443; otherwise it forwards
  # straight to the tracking server.
  default_action {
    type             = local.enable_https ? "redirect" : "forward"
    target_group_arn = local.enable_https ? null : aws_lb_target_group.ui.arn

    dynamic "redirect" {
      for_each = local.enable_https ? [1] : []
      content {
        port        = "443"
        protocol    = "HTTPS"
        status_code = "HTTP_301"
      }
    }
  }
}

resource "aws_lb_listener" "ui_https" {
  count             = local.enable_https ? 1 : 0
  load_balancer_arn = aws_lb.ui.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.mlflow[0].certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.ui.arn
  }
}

resource "aws_route53_record" "ui" {
  count   = local.enable_https ? 1 : 0
  zone_id = var.hosted_zone_id
  name    = var.domain_name
  type    = "A"

  alias {
    name                   = aws_lb.ui.dns_name
    zone_id                = aws_lb.ui.zone_id
    evaluate_target_health = true
  }
}
