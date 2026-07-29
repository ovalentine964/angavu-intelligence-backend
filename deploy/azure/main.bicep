// =============================================================================
// Angavu Intelligence Backend — Azure Infrastructure (Bicep)
// Deploys: PostgreSQL Flexible Server, Redis Cache, Container Registry, Container App
// Target: Azure Free Tier
// =============================================================================

@description('Location for all resources')
param location string = resourceGroup().location

@description('PostgreSQL administrator login name')
@minLength(1)
param administratorLogin string = 'angavu'

@description('PostgreSQL administrator login password')
@minLength(8)
@secure()
param administratorLoginPassword string

@description('Azure Container Registry name (globally unique, 5-50 alphanumeric)')
@minLength(5)
@maxLength(50)
param acrName string

@description('Container image to deploy')
param containerAppImage string = ''

@description('JWT secret for the application')
@secure()
param jwtSecret string = ''

@description('Encryption key (32 bytes)')
@secure()
param encryptionKey string = ''

@description('DeepSeek API key')
@secure()
param deepseekApiKey string = ''

@description('Qwen API key')
@secure()
param qwenApiKey string = ''

@description('Enable ClickHouse fallback (set ANALYTICS_BACKEND=postgresql)')
param usePostgresAnalytics bool = true

// ── Variables ────────────────────────────────────────────────────────────────
var environmentName = 'angavu-env'
var containerAppName = 'angavu-api'
var postgresServerName = 'angavu-pg'
var redisName = 'angavu-redis'
var dbName = 'angavu'
var tags = {
  project: 'angavu-intelligence'
  environment: 'production'
  managedBy: 'bicep'
}

// ── PostgreSQL Flexible Server (Free Tier) ───────────────────────────────────
resource postgresServer 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: postgresServerName
  location: location
  tags: tags
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    administratorLogin: administratorLogin
    administratorLoginPassword: administratorLoginPassword
    version: '16'
    storage: {
      storageSizeGB: 32
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: {
      mode: 'Disabled'
    }
    availabilityZone: ''
  }
}

resource angavuDb 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgresServer
  name: dbName
  properties: {
    charset: 'UTF8'
    collation: 'en_US.utf8'
  }
}

// Enable pgvector extension
resource pgvectorExtension 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: postgresServer
  name: 'shared_preload_libraries'
  properties: {
    value: 'pg_stat_statements,pgvector'
    source: 'user-override'
  }
}

// Allow Azure services to access PostgreSQL
resource postgresFirewall 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgresServer
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// ── Azure Cache for Redis (C0 Basic — Free Tier) ────────────────────────────
resource redisCache 'Microsoft.Cache/redis@2024-03-01-preview' = {
  name: redisName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'Basic'
      family: 'C'
      capacity: 0
    }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
  }
}

// ── Azure Container Registry ─────────────────────────────────────────────────
resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: acrName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
  }
}

// ── Log Analytics Workspace (for Container Apps logs) ────────────────────────
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'angavu-logs'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

// ── Container Apps Environment ───────────────────────────────────────────────
resource containerAppsEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// ── Container App ────────────────────────────────────────────────────────────
var postgresConnectionString = 'postgresql://${administratorLogin}:${administratorLoginPassword}@${postgresServer.name}.postgres.database.azure.com:5432/${dbName}?sslmode=require'
var redisConnectionString = '${redis.name}.redis.cache.windows.net:6380,password=${redisCache.listKeys().primaryKey},ssl=True,abortConnect=False'

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    managedEnvironmentId: containerAppsEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      registries: [
        {
          server: acr.properties.loginServer
          username: acr.name
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'acr-password'
          value: acr.listCredentials().passwords[0].value
        }
        {
          name: 'jwt-secret'
          value: jwtSecret
        }
        {
          name: 'encryption-key'
          value: encryptionKey
        }
        {
          name: 'deepseek-api-key'
          value: deepseekApiKey
        }
        {
          name: 'qwen-api-key'
          value: qwenApiKey
        }
        {
          name: 'database-url'
          value: postgresConnectionString
        }
        {
          name: 'redis-url'
          value: redisConnectionString
        }
      ]
    }
    template: {
      revisionSuffix: 'initial'
      containers: [
        {
          name: 'angavu-api'
          image: empty(containerAppImage) ? '${acr.properties.loginServer}/angavu-backend:latest' : containerAppImage
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            {
              name: 'DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'REDIS_URL'
              secretRef: 'redis-url'
            }
            {
              name: 'RUST_LOG'
              value: 'info'
            }
            {
              name: 'ANGAVU_HOST'
              value: '0.0.0.0'
            }
            {
              name: 'ANGAVU_PORT'
              value: '8000'
            }
            {
              name: 'JWT_SECRET'
              secretRef: 'jwt-secret'
            }
            {
              name: 'ENCRYPTION_KEY'
              secretRef: 'encryption-key'
            }
            {
              name: 'DEEPSEEK_API_KEY'
              secretRef: 'deepseek-api-key'
            }
            {
              name: 'QWEN_API_KEY'
              secretRef: 'qwen-api-key'
            }
            {
              name: 'ANALYTICS_BACKEND'
              value: usePostgresAnalytics ? 'postgresql' : 'clickhouse'
            }
            {
              name: 'PYTHONPATH'
              value: '/app/python'
            }
            {
              name: 'PYTHONUNBUFFERED'
              value: '1'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 15
              periodSeconds: 30
              timeoutSeconds: 5
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 3
        rules: [
          {
            name: 'http-rule'
            http: {
              metadata: {
                concurrentRequests: '100'
              }
            }
          }
        ]
      }
    }
  }
}

// ── RBAC: Allow Container App to pull from ACR ──────────────────────────────
resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(containerApp.id, acr.id, 'AcrPull')
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-a24a9c421210') // AcrPull
    principalId: containerApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Outputs ──────────────────────────────────────────────────────────────────
output containerAppUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
output postgresServerFqdn string = postgresServer.properties.fullyQualifiedDomainName
output redisHostName string = redisCache.properties.hostName
output acrLoginServer string = acr.properties.loginServer
output logAnalyticsCustomerId string = logAnalytics.properties.customerId
