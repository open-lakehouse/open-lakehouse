# ============================================================================
# ACM certificate (DNS-validated) — shared by the ALB (UI) and NLB (Connect).
# Recommend a wildcard cert_domain_name (e.g. *.openlakehousedemos.dev) so one
# cert covers both the UI and Connect subdomains. Gated on enable_https.
# ============================================================================
resource "aws_acm_certificate" "spark" {
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
    for dvo in aws_acm_certificate.spark[0].domain_validation_options :
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

resource "aws_acm_certificate_validation" "spark" {
  count                   = local.enable_https ? 1 : 0
  certificate_arn         = aws_acm_certificate.spark[0].arn
  validation_record_fqdns = [for r in aws_route53_record.cert_validation : r.fqdn]
}

# ============================================================================
# ALB — public master UI (HTTP, or HTTPS when a domain is configured).
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
  port        = var.master_ui_port
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = local.vpc_id
  tags        = var.tags

  health_check {
    path                = "/"
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
  # straight to the master UI.
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
  certificate_arn   = aws_acm_certificate_validation.spark[0].certificate_arn

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

# ============================================================================
# NLB — public Spark Connect gRPC endpoint.
# An NLB (L4) passes HTTP/2 through cleanly. With HTTPS enabled it terminates
# TLS on :443 (ALPN h2) and forwards plaintext h2c to the Connect server, so
# clients use sc://<connect_domain>:443 with SSL. Without HTTPS it forwards raw
# TCP on the gRPC port (sc://<nlb-dns>:<port>, no SSL).
# ============================================================================
resource "aws_lb" "connect" {
  count              = local.enable_connect ? 1 : 0
  name               = "${var.name_prefix}-connect"
  load_balancer_type = "network"
  internal           = false
  subnets            = local.subnet_ids
  tags               = var.tags
}

resource "aws_lb_target_group" "connect" {
  count       = local.enable_connect ? 1 : 0
  name        = "${var.name_prefix}-connect"
  port        = var.connect_grpc_port
  protocol    = "TCP"
  target_type = "ip"
  vpc_id      = local.vpc_id
  tags        = var.tags

  health_check {
    protocol            = "TCP"
    interval            = 30
    healthy_threshold   = 3
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "connect" {
  count             = local.enable_connect ? 1 : 0
  load_balancer_arn = aws_lb.connect[0].arn
  port              = local.enable_https ? 443 : var.connect_grpc_port
  protocol          = local.enable_https ? "TLS" : "TCP"
  ssl_policy        = local.enable_https ? "ELBSecurityPolicy-TLS13-1-2-2021-06" : null
  certificate_arn   = local.enable_https ? aws_acm_certificate_validation.spark[0].certificate_arn : null
  alpn_policy       = local.enable_https ? "HTTP2Preferred" : null

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.connect[0].arn
  }
}

resource "aws_route53_record" "connect" {
  count   = local.enable_connect_dns ? 1 : 0
  zone_id = var.hosted_zone_id
  name    = var.connect_domain_name
  type    = "A"

  alias {
    name                   = aws_lb.connect[0].dns_name
    zone_id                = aws_lb.connect[0].zone_id
    evaluate_target_health = true
  }
}
