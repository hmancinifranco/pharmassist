import {
  CognitoIdentityClient,
  GetIdCommand,
  GetCredentialsForIdentityCommand,
} from "@aws-sdk/client-cognito-identity";

const REGION = import.meta.env.VITE_AWS_REGION ?? "us-east-1";
const IDENTITY_POOL_ID = import.meta.env.VITE_IDENTITY_POOL_ID ?? "";
const USER_POOL_ID = import.meta.env.VITE_COGNITO_USER_POOL_ID ?? "";

/** Credenciales AWS temporales obtenidas via Cognito Identity Pool. */
export interface AwsCredentials {
  accessKeyId: string;
  secretAccessKey: string;
  sessionToken: string;
  expiration: Date;
}

let cachedCredentials: AwsCredentials | null = null;

const REFRESH_MARGIN_MS = 5 * 60 * 1000; // 5 minutos

/**
 * Determina si las credenciales cacheadas siguen siendo válidas.
 * Retorna true si faltan más de 5 minutos para que expiren.
 */
export function isCacheValid(
  expiration: Date,
  now: Date = new Date(),
): boolean {
  return expiration.getTime() - now.getTime() > REFRESH_MARGIN_MS;
}

/**
 * Intercambia un JWT (id_token) de Cognito User Pool por credenciales
 * AWS temporales via Cognito Identity Pool.
 *
 * Las credenciales se cachean y se renuevan automáticamente cuando
 * faltan menos de 5 minutos para su expiración.
 */
export async function getAwsCredentials(
  idToken: string,
): Promise<AwsCredentials> {
  if (cachedCredentials && isCacheValid(cachedCredentials.expiration)) {
    return cachedCredentials;
  }

  const client = new CognitoIdentityClient({ region: REGION });
  const providerName = `cognito-idp.${REGION}.amazonaws.com/${USER_POOL_ID}`;

  const { IdentityId } = await client.send(
    new GetIdCommand({
      IdentityPoolId: IDENTITY_POOL_ID,
      Logins: { [providerName]: idToken },
    }),
  );

  const { Credentials } = await client.send(
    new GetCredentialsForIdentityCommand({
      IdentityId: IdentityId!,
      Logins: { [providerName]: idToken },
    }),
  );

  if (!Credentials?.AccessKeyId || !Credentials.SecretKey || !Credentials.SessionToken) {
    throw new Error(
      "No se pudieron obtener credenciales para el modo voz. Intentá reloguearte.",
    );
  }

  cachedCredentials = {
    accessKeyId: Credentials.AccessKeyId,
    secretAccessKey: Credentials.SecretKey,
    sessionToken: Credentials.SessionToken,
    expiration: Credentials.Expiration ?? new Date(Date.now() + 3600_000),
  };

  return cachedCredentials;
}

/** Limpia el cache de credenciales. Llamar al hacer logout. */
export function clearCredentialsCache(): void {
  cachedCredentials = null;
}
