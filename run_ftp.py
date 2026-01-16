from pyftpdlib.authorizers import DummyAuthorizer
from pyftpdlib.handlers import FTPHandler
from pyftpdlib.servers import FTPServer
import os

def main():
    # Serve the MOCK_ROOT directory
    root_dir = os.path.join(os.getcwd(), 'scanner', 'MOCK_ROOT')
    
    if not os.path.exists(root_dir):
        print(f"Error: Directory {root_dir} not found!")
        return

    authorizer = DummyAuthorizer()
    # Add user with full read permissions
    authorizer.add_user("FTP_TEST", "FTP_TEST", root_dir, perm="elr")
    
    handler = FTPHandler
    handler.authorizer = authorizer
    
    # Listen on localhost port 2121
    address = ("127.0.0.1", 2121)
    server = FTPServer(address, handler)
    
    print(f"DTO FTP Server started on ftp://127.0.0.1:2121")
    print(f"Serving: {root_dir}")
    print("Press Ctrl+C to stop.")
    
    server.serve_forever()

if __name__ == '__main__':
    main()
