class MicroserviceRouter:
    """
    A router to control all database operations on models in the
    ubuntunow-platform applications.
    """
    route_app_labels = {'authentication': 'auth_db', 'products': 'product_db', 'orders': 'order_db', 'payments': 'payment_db', 'notifications': 'notification_db'}

    def db_for_read(self, model, **hints):
        if model._meta.app_label == 'users':
            if model._meta.model_name == 'store':
                return 'store_db'
            return 'auth_db'
        
        return self.route_app_labels.get(model._meta.app_label, 'default')

    def db_for_write(self, model, **hints):
        if model._meta.app_label == 'users':
            if model._meta.model_name == 'store':
                return 'store_db'
            return 'auth_db'
        
        return self.route_app_labels.get(model._meta.app_label, 'default')

    def allow_relation(self, obj1, obj2, **hints):
        # We allow relations across databases IF they are read-only OR we 
        # have turned off db_constraint=False on the ForeignKey explicitly.
        # Django supports this functionally.
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        # auth-service creates auth_db tables
        # store-service creates store_db tables, etc.
        # We assume the services run migrate against their specific DBs.
        if app_label == 'users':
            if model_name == 'store':
                return db == 'store_db'
            return db == 'auth_db'
        
        target_db = self.route_app_labels.get(app_label, 'default')
        if db == target_db:
            return True
        
        # We allow built-in Django apps to migrate on default
        if target_db == 'default' and db == 'default':
            return True

        return False
