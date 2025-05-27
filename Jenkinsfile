pipeline {
    agent { label 'docker' }

    triggers {
        pollSCM('H/5 * * * *') // Optional: webhooks are more efficient
    }

    environment {
        DOCKER_REGISTRY = 'registry.local'
        DOCKER_IMAGE = 'neodns'
        DOCKER_TAG = 'latest'

        // Define allowed branches as a comma-separated string
        ALLOWED_BRANCHES = 'main,dev,release'
    }

    stages {
        stage('Detect Branch') {
            steps {
                script {
                    // Use GIT_BRANCH environment variable for better reliability
                    env.BRANCH_NAME = env.GIT_BRANCH ?: sh(script: "git rev-parse --abbrev-ref HEAD", returnStdout: true).trim()
                    echo "Detected branch: ${env.BRANCH_NAME}"

                    // Strip 'origin/' from the branch name if it exists
                    env.BRANCH_NAME = env.BRANCH_NAME.replaceAll(/^origin\//, '')
                    echo "Normalized branch: ${env.BRANCH_NAME}"

                    // Convert allowed list to array and check if current branch is allowed
                    def allowed = env.ALLOWED_BRANCHES.tokenize(',')
                    env.IS_ALLOWED_BRANCH = allowed.contains(env.BRANCH_NAME).toString()
                    echo "Is allowed branch: ${env.IS_ALLOWED_BRANCH}"
                }
            }
        }

        stage('Build Docker Image') {
            when {
                expression { return env.IS_ALLOWED_BRANCH == 'true' }
            }
            steps {
                sh """
                    docker build -t ${DOCKER_REGISTRY}/${DOCKER_IMAGE}:${DOCKER_TAG} .
                """
            }
        }

        stage('Push Docker Image') {
            when {
                expression { return env.IS_ALLOWED_BRANCH == 'true' }
            }
            steps {
                sh """
                    docker push ${DOCKER_REGISTRY}/${DOCKER_IMAGE}:${DOCKER_TAG}
                """
            }
        }

        stage('Pull Image to Verify') {
            when {
                expression { return env.IS_ALLOWED_BRANCH == 'true' }
            }
            steps {
                sh """
                    docker pull ${DOCKER_REGISTRY}/${DOCKER_IMAGE}:${DOCKER_TAG}
                """
            }
        }

        stage('Skip Message (Not Allowed Branch)') {
            when {
                expression { return env.IS_ALLOWED_BRANCH == 'false' }
            }
            steps {
                echo "Branch '${env.BRANCH_NAME}' is not in allowed list: ${env.ALLOWED_BRANCHES}. Skipping pipeline steps."
            }
        }
    }

    post {
        always {
            sh 'docker system prune -af || true'
        }
    }
}
