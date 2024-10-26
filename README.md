# Kafka Performance Testing with Locust
This project define a Helm chart to install [Locust](https://locust.io) on Kubernetes cluster to test [Strimzi Kafka](https://strimzi.io).
## Components
This chart deploys
- K8s Services
  - 2 web ui services, for producer and consumer testing, respectively
  - if distributed mode used, 2 control services for locust masters to communicate with workers.
- Locust testing pods
  - 2 locust master pods, for producer and consumer testing, respectively
  - if distributed mode used, worker containers for producer and consumer testing.
## Preparation and Assumptions
1. Create Kafka user for testing
Use the following manifest to create the Kafka user. Setup the ACL so that the user has adequate permission to access the testing topic.  
e.g. the following manifest defines a Kafka user have access to all the topics.
```yaml
- apiVersion: kafka.strimzi.io/v1beta2
  kind: KafkaUser
  metadata:
    labels:
      strimzi.io/cluster: <cluster name>
    name: <kakfa user name>
    namespace: <kafka name space>
  spec:
    authentication:
      type: tls
    authorization:
      acls:
      - host: '*'
        operations:
        - All
        resource:
          name: '*'
          type: topic
      - host: '*'
        operations:
        - All
        resource:
          name: '*'
          type: group
      - host: '*'
        operations:
        - All
        resource:
          type: cluster
      - host: '*'
        operations:
        - All
        resource:
          name: '*'
          type: transactionalId
      type: simple
```
Creating a Kafka user will also create a secret with the same name, which contains the cert and SSL key of this user.  
e.g. if creating a user named 'perf-user', apart from the Kafka user resource, A secret named `perf-user` will also be created.
```shell
$ kubectl get ku perf-user -n kafka
NAME        CLUSTER       AUTHENTICATION   AUTHORIZATION   READY
perf-user   daisy-kafka   tls              simple          True
$ kubectl get secret perf-user -n kafka
NAME        TYPE     DATA   AGE
perf-user   Opaque   5      7d11h
```
Alternatively, use `kubectl create ku` to create the Kafka user, if no special ACL is required.
2. Create Kafka topic for testing
Adjust partitions and replicas to fit for the testing purpose.
```yaml
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: <topic name>
  namespace: <Kafka name space>
  labels:
    strimzi.io/cluster: <Kafka cluster name>
spec:
  partitions: <topic partitions>
  replicas: <message replicas>
```
Alternatively use `kubectl creat kt` to create a topic
## Key Parameters
all the configuration parameters are stored in [values.yaml](values.yaml)
- kafka_test.data_per_user_mb  
The data of each Locust user will produce or consume, default is 100(MB)
- kafka_test.msg_size_kb: 100  
Size of each Kafka message, default is 100KB
- kafka_test.producer.ack_all  
kafka producer client config, boolean value
- kafka_test.producer.workers
number of producer testing pod, if > 1, locust will be deployed as distributed mode, i.e with 1 master pod and multiple worker pod; Otherwise Locust will deploy as standalone mode, i.e. only 1 pod for testing.
- kafka_test.consumer.workers  
similar to `kafka_test.producer.workers`, but for consumer client
## Deployment
```shell
helm install locust-kafka .
```
## Verification
Connect to the producer and consumer tester Web GUI service, by default they are on port 8089, e.g.  
`http://172.20.14.12:8089`  
`http://172.20.14.13:8089`
```shell
$ kubectl get svc -n kafka
NAME                             TYPE           CLUSTER-IP       EXTERNAL-IP    PORT(S)                               AGE
locust-kafka-svc-consumer        LoadBalancer   10.200.238.87    172.20.14.13   8089:30266/TCP                        5h5m
locust-kafka-svc-producer        LoadBalancer   10.200.237.122   172.20.14.12   8089:32702/TCP                        5h5m
```