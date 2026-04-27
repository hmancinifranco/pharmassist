import {
  CognitoIdentityProviderClient,
  InitiateAuthCommand,
  type InitiateAuthCommandOutput,
} from "@aws-sdk/client-cognito-identity-provider";

const REGION = import.meta.env.VITE_AWS_REGION ?? "us-east-1";
const USER_POOL_CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID ?? "";

const cognitoClient = new CognitoIdentityProviderClient({ region: REGION });

export interface AuthTokens {
  idToken: string;
  accessToken: string;
  refreshToken: string;
  expiresIn: number;
}

export async function login(email: string, password: string): Promise<AuthTokens> {
  const command = new InitiateAuthCommand({
    AuthFlow: "USER_PASSWORD_AUTH",
    ClientId: USER_POOL_CLIENT_ID,
    AuthParameters: { USERNAME: email, PASSWORD: password },
  });
  const response: InitiateAuthCommandOutput = await cognitoClient.send(command);
  const result = response.AuthenticationResult!;
  return {
    idToken: result.IdToken!,
    accessToken: result.AccessToken!,
    refreshToken: result.RefreshToken!,
    expiresIn: result.ExpiresIn ?? 3600,
  };
}

export async function refreshSession(refreshToken: string): Promise<AuthTokens> {
  const command = new InitiateAuthCommand({
    AuthFlow: "REFRESH_TOKEN_AUTH",
    ClientId: USER_POOL_CLIENT_ID,
    AuthParameters: { REFRESH_TOKEN: refreshToken },
  });
  const response = await cognitoClient.send(command);
  const result = response.AuthenticationResult!;
  return {
    idToken: result.IdToken!,
    accessToken: result.AccessToken!,
    refreshToken: refreshToken, // refresh token doesn't change
    expiresIn: result.ExpiresIn ?? 3600,
  };
}

export function parseJwt(token: string): Record<string, unknown> {
  const base64Url = token.split(".")[1];
  const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
  return JSON.parse(atob(base64));
}

export function getApmIdFromToken(idToken: string): string {
  const claims = parseJwt(idToken);
  return (claims["custom:apm_id"] as string) ?? "";
}
