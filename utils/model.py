from django.db import models
import django.utils.timezone as timezone
from django.db.models.query import QuerySet

# 自定义软删除查询基类


class SoftDeletableQuerySetMixin(object):
    '''
    QuerySet for SoftDeletableModel. Instead of removing instance sets
    its ``is_deleted`` field to True.
    '''

    def delete(self, soft=True):
        '''
        Soft delete objects from queryset (set their ``is_deleted``
        field to True)
        '''
        if soft:
            self.update(is_deleted=True)
        else:
            return super(SoftDeletableQuerySetMixin, self).delete()


class SoftDeletableQuerySet(SoftDeletableQuerySetMixin, QuerySet):
    pass


class SoftDeletableManagerMixin(object):
    '''
    Manager that limits the queryset by default to show only not deleted
    instances of model.
    '''
    _queryset_class = SoftDeletableQuerySet

    def get_queryset(self, all=False):
        '''
        Return queryset limited to not deleted entries.
        '''
        kwargs = {'model': self.model, 'using': self._db}
        if hasattr(self, '_hints'):
            kwargs['hints'] = self._hints
        if all:
            return self._queryset_class(**kwargs)
        return self._queryset_class(**kwargs).filter(is_deleted=False)


class SoftDeletableManager(SoftDeletableManagerMixin, models.Manager):
    pass


class BaseModel(models.Model):
    """
    基本表
    """
    create_time = models.DateTimeField(
        default=timezone.now, verbose_name='创建时间', help_text='创建时间')
    update_time = models.DateTimeField(
        auto_now=True, verbose_name='修改时间', help_text='修改时间')
    is_deleted = models.BooleanField(
        default=False, verbose_name='删除标记', help_text='删除标记')

    class Meta:
        abstract = True

class AllObjectsManager(SoftDeletableManager):
    def get_queryset(self):
        # 回傳所有資料，不論 is_deleted
        return super().get_queryset(all=True)

class SoftModel(BaseModel):
    """
    支援軟刪除的基本表
    """
    class Meta:
        abstract = True

    # 預設 manager：只會拿 is_deleted=False 的資料
    objects = SoftDeletableManager()

    # 額外公開一個 manager：拿所有資料（包含 is_deleted=True）
    all_objects = AllObjectsManager()

    def delete(self, using=None, soft=True, *args, **kwargs):
        '''
        預設為軟刪除，若需永久刪除請傳入 soft=False
        '''
        if soft:
            self.is_deleted = True
            self.save(using=using)
        else:
            return super(SoftModel, self).delete(using=using, *args, **kwargs)







