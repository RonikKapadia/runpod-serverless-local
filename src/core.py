from .endpoint import Endpoint, EndpointConfig

class RunpodServerlessLocal():
    def __init__(self):
        self.endpoints: dict[str, Endpoint] = {}

    def create_endpoint(self, endpoint_config: EndpointConfig):
        self.endpoints[endpoint_config.endpoint_id] = Endpoint(endpoint_config)
    
    def get_endpoint(self, endpoint_id: str):
        return self.endpoints[endpoint_id]

    def startup(self):
        for endpoint in self.endpoints.values():
            endpoint.startup()

    def shutdown(self):
        for endpoint in self.endpoints.values():
            endpoint.shutdown()