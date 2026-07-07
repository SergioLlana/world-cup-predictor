#!/usr/bin/env bash
#
# Phase 2 of docs/aws-migration-plan.md: the CloudFront distribution that serves
# the private wcpred-site bucket over HTTPS to the public. Idempotent — creates
# the Origin Access Control, the distribution, and the bucket policy only if
# they are missing, so re-running is safe.
#
#   - CloudFront OAC (SigV4, S3) so CloudFront can read the private bucket
#   - Distribution: default root index.html, HTTPS-only, a short-TTL behaviour
#     for api/* (JSON refreshed daily) and a long TTL for the immutable assets
#   - Bucket policy on wcpred-site granting that distribution GetObject
#   - Distribution id saved to SSM /wcpred/cloudfront-distribution-id for
#     publish_site.sh (invalidation) to discover
#
# Usage: scripts/aws/20_site.sh
#
# Needs a configured CLI profile (default 'wcpred'; see env.sh). CloudFront is a
# global service, so its calls ignore AWS_REGION.

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./env.sh
cd ../..

DIST_PARAM="/wcpred/cloudfront-distribution-id"
OAC_NAME="wcpred-oac"
COMMENT="wcpred static site"
# Regional endpoint (not the global one) is required for an S3 origin with OAC.
ORIGIN_DOMAIN="${SITE_BUCKET}.s3.${AWS_REGION}.amazonaws.com"
ORIGIN_ID="wcpred-site-s3"

# ------------------------------------------------------------------- OAC
oac_id="$(aws cloudfront list-origin-access-controls \
  --query "OriginAccessControlList.Items[?Name=='$OAC_NAME'].Id | [0]" \
  --output text)"
if [ "$oac_id" = "None" ] || [ -z "$oac_id" ]; then
  oac_id="$(aws cloudfront create-origin-access-control \
    --origin-access-control-config "{
      \"Name\": \"$OAC_NAME\",
      \"Description\": \"wcpred site OAC\",
      \"SigningProtocol\": \"sigv4\",
      \"SigningBehavior\": \"always\",
      \"OriginAccessControlOriginType\": \"s3\"}" \
    --query "OriginAccessControl.Id" --output text)"
  echo "OAC $OAC_NAME: created ($oac_id)"
else
  echo "OAC $OAC_NAME: already exists ($oac_id)"
fi

# ------------------------------------------------------------- distribution
dist_id="$(aws cloudfront list-distributions \
  --query "DistributionList.Items[?Comment=='$COMMENT'].Id | [0]" \
  --output text 2>/dev/null || true)"

if [ "$dist_id" = "None" ] || [ -z "$dist_id" ]; then
  # CachingOptimized and CachingDisabled are AWS-managed cache policies (stable
  # well-known ids). api/* uses CachingDisabled + short TTLs so a daily publish
  # shows up quickly; the rest (hashless static assets) is CachingOptimized and
  # relies on the publish-time invalidation.
  CACHING_OPTIMIZED="658327ea-f89d-4fab-a63d-7e88639e58f6"
  CACHING_DISABLED="4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
  ref="wcpred-$(date +%s)"
  # Custom domain (wc-pred.com): serve it with the ACM cert (us-east-1, arn in
  # SSM) when present, else fall back to the default *.cloudfront.net cert. The
  # cert must already be ISSUED — request it with request-certificate + the DNS
  # validation CNAMEs before this runs (the DNS lives at the domain's registrar).
  cert_arn="$(aws ssm get-parameter --name /wcpred/acm-cert-arn \
    --query Parameter.Value --output text 2>/dev/null || true)"
  if [ -n "$cert_arn" ] && [ "$cert_arn" != "None" ]; then
    aliases_json='"Aliases": {"Quantity": 2, "Items": ["wc-pred.com", "www.wc-pred.com"]},'
    viewer_cert="{\"ACMCertificateArn\": \"$cert_arn\", \"SSLSupportMethod\": \"sni-only\", \"MinimumProtocolVersion\": \"TLSv1.2_2021\", \"Certificate\": \"$cert_arn\", \"CertificateSource\": \"acm\"}"
  else
    aliases_json=''
    viewer_cert='{"CloudFrontDefaultCertificate": true}'
  fi
  config="$(cat <<JSON
{
  "CallerReference": "$ref",
  "Comment": "$COMMENT",
  "Enabled": true,
  "DefaultRootObject": "index.html",
  $aliases_json
  "ViewerCertificate": $viewer_cert,
  "Origins": {"Quantity": 1, "Items": [{
    "Id": "$ORIGIN_ID",
    "DomainName": "$ORIGIN_DOMAIN",
    "OriginAccessControlId": "$oac_id",
    "S3OriginConfig": {"OriginAccessIdentity": ""}
  }]},
  "DefaultCacheBehavior": {
    "TargetOriginId": "$ORIGIN_ID",
    "ViewerProtocolPolicy": "redirect-to-https",
    "CachePolicyId": "$CACHING_OPTIMIZED",
    "Compress": true
  },
  "CacheBehaviors": {"Quantity": 1, "Items": [{
    "PathPattern": "api/*",
    "TargetOriginId": "$ORIGIN_ID",
    "ViewerProtocolPolicy": "redirect-to-https",
    "CachePolicyId": "$CACHING_DISABLED",
    "Compress": true
  }]},
  "PriceClass": "PriceClass_100"
}
JSON
)"
  dist_id="$(aws cloudfront create-distribution \
    --distribution-config "$config" \
    --query "Distribution.Id" --output text)"
  echo "distribution: created ($dist_id)"
else
  echo "distribution: already exists ($dist_id)"
fi

dist_domain="$(aws cloudfront get-distribution --id "$dist_id" \
  --query "Distribution.DomainName" --output text)"
dist_arn="$(aws cloudfront get-distribution --id "$dist_id" \
  --query "Distribution.ARN" --output text)"

aws ssm put-parameter --name "$DIST_PARAM" --type String \
  --value "$dist_id" --overwrite > /dev/null
echo "ssm $DIST_PARAM: $dist_id"

# ------------------------------------------------------------ bucket policy
# Let only this distribution read the private site bucket (OAC → SourceArn).
policy="$(cat <<JSON
{
  "Version": "2012-10-17",
  "Statement": [{
    "Sid": "AllowCloudFrontOAC",
    "Effect": "Allow",
    "Principal": {"Service": "cloudfront.amazonaws.com"},
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::$SITE_BUCKET/*",
    "Condition": {"StringEquals": {"AWS:SourceArn": "$dist_arn"}}
  }]
}
JSON
)"
aws s3api put-bucket-policy --bucket "$SITE_BUCKET" --policy "$policy"
echo "bucket policy on $SITE_BUCKET: set (only $dist_id can read)"

echo
echo "Done. Public URL (once the distribution finishes deploying, ~15 min):"
echo "  https://$dist_domain"
cert_arn="$(aws ssm get-parameter --name /wcpred/acm-cert-arn \
  --query Parameter.Value --output text 2>/dev/null || true)"
if [ -n "$cert_arn" ] && [ "$cert_arn" != "None" ]; then
  echo "  https://wc-pred.com  (CNAME @ + www -> $dist_domain at the registrar, DNS-only)"
fi
