# Local-first AWS strategy

Status: recommendation only. No resources, credentials, region, model entitlement, costs or deployment have been inspected/configured. Exact event requirements have not been independently verified. AWS use is planned to be substantive, but eligibility must be confirmed against the organizer's actual rules.

## Scope by gate

G1 needs no AWS setup, toolkit installation, cloud calls or deployment. Use memory for session state unless SQLite is equally quick. G2 adds Bedrock and the real agents/model behind the existing seams. G3 handles only the hosting, persistence and access controls that the actual demo needs; EC2 remains the preferred simple hosting option. Cognito and additional infrastructure remain deferred unless event requirements justify them. The deployment details below are later guidance, not baseline acceptance criteria.

## Decision

Use **Amazon Bedrock for assessment and tutoring inference**. Later deploy **the same single application container on one EC2 instance**, with simple SQLite on an EBS-backed host directory if persistence is useful; otherwise use fresh in-memory demo sessions. The backend uses an instance IAM role for AWS access. These choices keep the meaningful model work on AWS and avoid changing the application architecture for deployment.

The recommendation is based on local/cloud parity and this team's constraints, not a claim that EC2 is universally the easiest host. A single operator must handle instance setup, runtime updates and restart. Timebox that work; if workshop account restrictions block hosting, preserve the laptop + Bedrock demo and explicitly report that AWS hosting remains incomplete.

## Service-by-service tradeoffs

| Service | Demo/judging value | Effort and integration risk | Local substitute / decision |
| --- | --- | --- | --- |
| Bedrock | Real AWS inference drives diagnosis and teaching; show actual provider/model and tool decisions | Requires authorized model/region, quotas, validated structured output, timeouts | Fake adapter by default; OpenAI adapter by explicit configuration. Include in live MVP |
| EC2 | Runs the same complete demo on AWS | One host to configure; operator responsible for access, process restart and OS | Native local app or same Docker container. Include after live loop works |
| EBS attached to EC2 | Can persist SQLite if the deployed demo needs it | Verify the disk mount only when persistence is adopted | Local memory in G1; local disk later. No separate database service |
| IAM instance role | Allows backend Bedrock calls without shipping AWS keys in the image | Scope permissions to required model/profile and API actions; verify container credential access | Temporary developer credentials via normal AWS SDK chain; no role needed for fake mode |
| Cognito | Adopted: the team decided real per-user accounts/login are a genuine product requirement, not just a demo-access gate | User Pool + App Client (Hosted UI, Authorization Code + PKCE, no client secret in the SPA); backend verifies the Cognito ID token's signature/claims via JWKS | User Pool created via AWS CLI runbook (docs/AWS.md below); backend/app/auth/cognito.py verifies tokens; anonymous session_id remains the fallback when no token is presented, so G1's dummy loop is unaffected |
| Bedrock Agents / AgentCore | Potential managed orchestration/hosting capabilities | Another lifecycle and execution model before the core loop is proven | Defer; bounded Python coordinator with provider calls is sufficient |
| S3 / Bedrock Knowledge Bases / vector storage | Useful for large document collections and retrieval | No need with a tiny authored bank; ingestion/retrieval creates another failure surface | Defer; versioned local content files |
| DynamoDB | Adopted: real persistence for session/learner state so data survives a backend restart, tied to the Cognito user when signed in | One table, partition key `session_id`, on-demand billing; `backend/app/storage/dynamo.py` implements the same three-method seam as MemoryStore | Table created via AWS CLI runbook below; selected only when `DYNAMODB_TABLE_NAME` is set, so the in-memory default is unchanged when unconfigured |
| RDS / ElastiCache | Would support later multi-instance persistence/caching | Adds local emulation, credentials and storage rewrites | Defer; DynamoDB covers the hackathon's persistence need |
| Lambda / API Gateway / Step Functions / ECS / EKS | Useful in other hosting patterns | Multiple deployment concepts with little visible demo benefit here | Defer; one process/container |

EBS is persistent block storage, but deleting/terminating resources can still delete a volume depending on configuration; it is not a backup strategy. Verify lifecycle settings and export the synthetic demo state before teardown. [AWS EBS documentation](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/storage_ebs.html).

## Agent Toolkit for AWS — development tooling only

Use [Agent Toolkit for AWS](https://docs.aws.amazon.com/agent-toolkit/latest/userguide/what-is-agent-toolkit.html) to help Codex/Claude consult current AWS documentation, use relevant AWS skills and configure AWS resources during authorized development. AWS describes it as coding-agent tooling with MCP, skills and plugins. It is not Assessment, Tutor or Curriculum/Planning, not part of the request path, and not a backend dependency.

When AWS work begins, SWE1/SWE3 check whether it is already available. If useful and authorized, follow the official [AWS CLI setup guide](https://docs.aws.amazon.com/agent-toolkit/latest/userguide/aws-cli.html): `aws configure agent-toolkit` configures supported coding agents and skills with AWS CLI 2.35.0 or later. This is a future setup option, not a command run by this documentation task. Keep personal configuration and credentials out of the repository; use only the team's authorized account/permissions.

Use the toolkit to support the chosen Bedrock/local-first plan. Its broader infrastructure guidance does not make AgentCore, Cognito, extra services or production architecture necessary. If toolkit setup slows progress, use official AWS documentation and normal SDK/CLI tools; it never blocks G1 or the local dummy loop.

## Provider seam

After G1, agree the small `complete(...)` provider adapter described in CONTRACTS.md when the first real role needs it; do not build a generic ModelRequest/ModelResult framework during G1. SWE3 owns all adapters; other modules never import provider SDKs. Bedrock's [Converse API](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html) supports a common conversation request shape and tool configuration. Use a model verified to support the required features in the team's region; model availability is not assumed.

OpenAI uses the Responses API through its own adapter. Both adapters map to the same normalized text/tool blocks and schema-validated JSON. Do not assume identical JSON-mode support, tool semantics or outputs across providers. Avoid specifying a model ID until the team has checked actual access and a short educational sample.

Planned configuration, to be implemented after approval:

| Setting | Meaning |
| --- | --- |
| `APP_MODE=dummy` | Default; all domain fakes; runtime cannot call cloud services |
| `APP_MODE=live` | Real modules required; startup rejects any fake learner/policy |
| `MODEL_PROVIDER` | One of `fake`, `bedrock`, `openai`; fake allowed only with dummy; Bedrock/OpenAI only with live |
| `AWS_REGION`, `BEDROCK_MODEL_ID` | Explicitly chosen region and compatible model/inference profile |
| `OPENAI_MODEL`, `OPENAI_API_KEY` | Alternative provider config; secret is server-only |
| `DATABASE_PATH` | Only if SQLite is adopted: local writable path or deployed volume path |
| `TURN_TIMEOUT_SECONDS`, `MAX_MODEL_CALLS` | Default planned caps of 20 seconds and four calls |
| `COGNITO_USER_POOL_ID`, `COGNITO_APP_CLIENT_ID` | Enables backend ID-token verification when both are set; unset means anonymous-only, matching the original G1 session model |
| `COGNITO_DOMAIN` | The User Pool's Hosted UI domain; used by the frontend to build the login redirect URL |
| `DYNAMODB_TABLE_NAME` | Enables DynamoDB-backed session persistence when set; unset means in-memory only, matching the original G1 storage seam |

### Cognito setup runbook (run by a human, not the coding agent)

Creating real AWS resources is a deliberate, human-approved action, not something the coding session executes unattended. From a terminal with the team's authorized AWS CLI profile:

```sh
aws cognito-idp create-user-pool --pool-name minds-and-machines \
  --auto-verified-attributes email \
  --username-attributes email \
  --region us-east-1

# Note the returned UserPool.Id, then create a public (no-secret) SPA app client:
aws cognito-idp create-user-pool-client --user-pool-id <POOL_ID> \
  --client-name web --no-generate-secret \
  --allowed-o-auth-flows code --allowed-o-auth-scopes openid email \
  --allowed-o-auth-flows-user-pool-client \
  --callback-urls http://127.0.0.1:5173/ --logout-urls http://127.0.0.1:5173/ \
  --supported-identity-providers COGNITO \
  --region us-east-1

# Give the pool a Hosted UI domain (must be globally unique):
aws cognito-idp create-user-pool-domain --domain minds-and-machines-<unique-suffix> \
  --user-pool-id <POOL_ID> --region us-east-1
```

Record the pool ID, app client ID and domain as `COGNITO_USER_POOL_ID`, `COGNITO_APP_CLIENT_ID` and `COGNITO_DOMAIN`. Verify the Workshop Studio participant role actually permits `cognito-idp:Create*` before running this; if it does not, request a scoped exception rather than switching credentials.

### DynamoDB table runbook (also run by a human)

```sh
aws dynamodb create-table --table-name minds-and-machines-sessions \
  --attribute-definitions AttributeName=session_id,AttributeType=S \
  --key-schema AttributeName=session_id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

Set `DYNAMODB_TABLE_NAME=minds-and-machines-sessions` before starting the backend. On-demand billing means no cost while idle and no capacity planning for a hackathon's traffic.

Do not automatically switch Bedrock to OpenAI on a failed request. That hides the provider in the demo and may send answers to a different provider unexpectedly. Use a curated response with a degraded indicator; an operator can explicitly choose OpenAI for a later session. Record the actual provider/model per call. Never say a fallback run satisfies an unverified AWS judging rule.

## What runs where

| Mode | Local machine | AWS |
| --- | --- | --- |
| G1 and optional dummy CI | UI, API, fake roles/model/policy, tiny content fixture, in-memory state, checks | Nothing |
| Live developer demo after G1 | UI, API, real modules, content, memory or simple SQLite | Bedrock inference only |
| Later deployed demo | Browser | EC2 app/container; memory or SQLite on EBS if useful; Bedrock inference; IAM role |

Local development uses temporary AWS credentials supplied by the developer's authorized SDK profile/session. Do not write them into tracked files or inspect personal credentials merely to document architecture. On EC2, use temporary role credentials instead of copied long-lived keys; AWS documents this [instance role mechanism](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html).

## Deployment plan for the later authorized phase

1. SWE1/SWE3 confirm account permissions, allowed region/model, model access and quota, session duration, event rules and the agreed spending limit. Run one controlled Bedrock assessment/tool-use smoke and record latency/validation results. No generic model benchmark project.
2. Build one container with the frontend assets served by FastAPI. Pin dependencies; target the EC2 architecture explicitly so an Apple Silicon build does not fail on the deployment host. Test the container locally first.
3. Deploy one instance with one application worker and a restart policy. Build from a reviewed Git SHA or transfer that exact built image; no registry is required for the first demo. If adopting SQLite, mount its directory from the EBS-backed host filesystem rather than the container layer. Otherwise document that a restart requires a new demo session.
4. Attach a least-privilege IAM role. Test SDK credentials from inside the running container, not just the host. Allow only required inbound access. Keep Bedrock and OpenAI secrets server-side.
5. Default presentation path: presenter browser through an SSH tunnel to the AWS app, with SSH limited to the team. If judges require a public URL, SWE1 adds an HTTPS reverse proxy with a known hostname and a demo access gate plus modest request limits. Verify this before advertising public access; never expose an unlimited unauthenticated paid-model endpoint.
6. Run the dummy smoke against the deployed build, then the live Bedrock scenario and a failure/fallback rehearsal. Confirm the selected state behavior (restart persistence only if implemented), separate demo sessions, and the actual Git SHA/provider. Rehearse one provider fallback; a failure-simulation matrix is unnecessary.
7. Keep the last good image/build and local offline demo. Roll back by restoring the known build, preserving compatible data or using fresh synthetic sessions. After the event, terminate approved resources and verify remaining storage/address charges.

Do not add a custom domain, load balancer, multi-instance scaling, production identity or automated infrastructure framework unless required for the actual presentation. A public HTTPS endpoint is a later hosting condition, not necessary to validate the core loop locally.

## Operational limits

Use synthetic/adult demo inputs and disclose when text is sent to a provider. Log structured stage/provider/model/latency/token counts and short error codes, not raw answers. Cap input length, model output tokens, calls per turn and session request rate; configure a simple operator kill switch for live inference. Rehearse a credential expiry or quota failure. Exact account costs/credits remain unverified; no free-tier or budget guarantee is made.
