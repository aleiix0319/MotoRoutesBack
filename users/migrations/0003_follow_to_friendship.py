"""Follow pasa a ser Friendship: la misma tabla, ahora con estado.

Se renombra en vez de borrar y crear para no perder los datos de desarrollo:
los seguimientos mutuos que ya existian se convierten en amistades aceptadas
(que es lo que significaban) y los de un solo sentido se quedan como solicitud
pendiente, que es lo mas parecido a lo que eran.
"""
from django.conf import settings
from django.db import migrations, models


def follows_to_friendships(apps, schema_editor):
    Friendship = apps.get_model('users', 'Friendship')

    # Una amistad es una sola fila, asi que de cada par mutuo sobrevive la mas
    # antigua (la que pidio primero) y la otra sobra.
    first_of_pair = {}

    for row in Friendship.objects.order_by('id'):
        pair = frozenset((row.from_user_id, row.to_user_id))

        if pair in first_of_pair:
            original = first_of_pair[pair]
            original.status = 'accepted'
            original.responded_at = row.created_at
            original.save(update_fields=['status', 'responded_at'])
            row.delete()
        else:
            first_of_pair[pair] = row


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('users', '0002_follow_follow_unique_follow_follow_no_self_follow'),
    ]

    operations = [
        # Las restricciones y los indices nombran las columnas viejas: fuera
        # antes de renombrar, y se vuelven a poner al final ya con los nombres
        # nuevos.
        migrations.RemoveConstraint(
            model_name='follow',
            name='unique_follow',
        ),
        migrations.RemoveConstraint(
            model_name='follow',
            name='no_self_follow',
        ),
        migrations.RemoveIndex(
            model_name='follow',
            name='users_follo_followe_4166a2_idx',
        ),
        migrations.RemoveIndex(
            model_name='follow',
            name='users_follo_followi_f3cd22_idx',
        ),
        migrations.RenameModel(
            old_name='Follow',
            new_name='Friendship',
        ),
        migrations.RenameField(
            model_name='friendship',
            old_name='follower',
            new_name='from_user',
        ),
        migrations.RenameField(
            model_name='friendship',
            old_name='following',
            new_name='to_user',
        ),
        migrations.AlterField(
            model_name='friendship',
            name='from_user',
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name='friend_requests_sent',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='friendship',
            name='to_user',
            field=models.ForeignKey(
                on_delete=models.deletion.CASCADE,
                related_name='friend_requests_received',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='friendship',
            name='status',
            field=models.CharField(
                choices=[('pending', 'Pending'), ('accepted', 'Accepted')],
                db_index=True,
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='friendship',
            name='responded_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name='friendship',
            index=models.Index(
                fields=['to_user', 'status'],
                name='users_frien_to_user_db034b_idx',
            ),
        ),
        migrations.AddIndex(
            model_name='friendship',
            index=models.Index(
                fields=['from_user', 'status'],
                name='users_frien_from_us_9e7907_idx',
            ),
        ),
        migrations.RunPython(
            follows_to_friendships,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='friendship',
            constraint=models.UniqueConstraint(
                fields=('from_user', 'to_user'),
                name='unique_friendship',
            ),
        ),
        migrations.AddConstraint(
            model_name='friendship',
            constraint=models.CheckConstraint(
                check=models.Q(('from_user', models.F('to_user')), _negated=True),
                name='no_self_friendship',
            ),
        ),
    ]
