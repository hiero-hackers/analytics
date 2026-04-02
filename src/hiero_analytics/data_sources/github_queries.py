"""
GraphQL queries to later be used for fetching data from GitHub
"""


REPOS_QUERY: str = """
query($org:String!,$cursor:String){
  organization(login:$org){
    repositories(first:100, after:$cursor){
      pageInfo{
        hasNextPage
        endCursor
      }
      nodes{
        name
      }
    }
  }
  rateLimit{
    limit
    remaining
    cost
    resetAt
  }
}
"""

ISSUES_QUERY: str = """
query($owner:String!,$repo:String!,$cursor:String,$states:[IssueState!]){
  repository(owner:$owner,name:$repo){
    issues(first:100, after:$cursor, states:$states){
      pageInfo{
        hasNextPage
        endCursor
      }
      nodes{
        number
        title
        state
        createdAt
        closedAt
        labels(first:10){
          nodes{
            name
          }
        }
      }
    }
  }
  rateLimit{
    limit
    remaining
    cost
    resetAt
  }
}
"""

MERGED_PR_QUERY: str = """
query($owner:String!, $repo:String!, $cursor:String) {
  repository(owner:$owner, name:$repo) {
    pullRequests(
      first:100
      after:$cursor
      states:MERGED
      orderBy:{field:UPDATED_AT, direction:DESC}
    ) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        number
        createdAt
        mergedAt

        author {
          login
        }

        additions
        deletions
        changedFiles
        closingIssuesReferences(first:10) {
          nodes {
            number
            labels(first:10) {
              nodes {
                name
              }
            }
          }
        }
      }
    }
  }
  rateLimit{
    limit
    remaining
    cost
    resetAt
  }
}
"""


CONTRIBUTOR_ACTIVITY_QUERY: str = """
query($owner:String!, $repo:String!, $cursor:String) {
  repository(owner:$owner, name:$repo) {
    pullRequests(
      first:100
      after:$cursor
      orderBy:{field:UPDATED_AT, direction:DESC}
    ) {
      pageInfo {
        hasNextPage
        endCursor
      }
      nodes {
        number
        createdAt
        updatedAt
        mergedAt
        author {
          login
        }
        mergedBy {
          login
        }
        reviews(first:100) {
          nodes {
            state
            submittedAt
            author {
              login
            }
          }
        }
      }
    }
  }
  rateLimit{
    limit
    remaining
    cost
    resetAt
  }
}
"""


CONTRIBUTOR_MERGED_PRS_COUNT_QUERY: str = """
query($searchQuery:String!) {
  search(type:ISSUE, query:$searchQuery, first:0) {
    issueCount
  }
  rateLimit{
    limit
    remaining
    cost
    resetAt
  }
}
"""
