# GQL queries needed for the EGS API

uplay_codes_query = '''
query partnerIntegrationQuery($accountId: String!) {
  PartnerIntegration {
    accountUplayCodes(accountId: $accountId) {
      epicAccountId
      gameId
      uplayAccountId
      regionCode
      redeemedOnUplay
      redemptionTimestamp
    }
  }
}
'''

uplay_redeem_query = '''
mutation redeemAllPendingCodes($accountId: String!, $uplayAccountId: String!) {
  PartnerIntegration {
    redeemAllPendingCodes(accountId: $accountId, uplayAccountId: $uplayAccountId) {
      data {
        epicAccountId
        uplayAccountId
        redeemedOnUplay
        redemptionTimestamp
      }
      success
    }
  }
}
'''

uplay_claim_query = '''
mutation claimUplayCode($accountId: String!, $uplayAccountId: String!, $gameId: String!) {
  PartnerIntegration {
    claimUplayCode(
      accountId: $accountId
      uplayAccountId: $uplayAccountId
      gameId: $gameId
    ) {
      data {
        assignmentTimestam
        epicAccountId
        epicEntitlement {
          entitlementId
          catalogItemId
          entitlementName
          country
        }
        gameId
        redeemedOnUplay
        redemptionTimestamp
        regionCode
        uplayAccountId
      }
      success
    }
  }
}
'''